"""Double-entry ledger.

Rules:
- Every money movement is one journal entry with at least two postings; debits equal credits
  (checked here and again by a database trigger at commit).
- Postings and entries are never changed or deleted. Mistakes are corrected by a new entry.
- Each account keeps a cached `balance` in its normal side (assets: debits - credits; liabilities and
  revenue: credits - debits). It is updated in the same transaction, under a row lock, so concurrent
  payments cannot overspend. `integrity_report` re-derives every balance from the postings.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import case, func, insert, select
from sqlalchemy.orm import Session

from app import clock
from app.errors import AppError, InsufficientFunds
from app.models import JournalEntry, LedgerAccount, Posting
from app.money import ZERO, is_cents

Side = Literal["D", "C"]
NORMAL_SIDE: dict[str, Side] = {"asset": "D", "expense": "D", "liability": "C", "revenue": "C", "equity": "C"}

TRUST_BANK = "SYS:TRUST_BANK"
ESCROW = "SYS:ESCROW"
WITHDRAWALS_PENDING = "SYS:WITHDRAWALS_PENDING"
FEE_REVENUE = "SYS:FEE_REVENUE"

# Per-user accounts: (purpose, kind, name)
USER_ACCOUNTS = (
    ("wallet", "liability", "Stars wallet"),
    ("receivable", "asset", "Penalties owed to the platform"),
)


@dataclass(frozen=True)
class Line:
    account_id: uuid.UUID
    side: Side
    amount: Decimal
    description: str = ""


def debit(account_id: uuid.UUID, amount: Decimal, description: str = "") -> Line:
    return Line(account_id, "D", amount, description)


def credit(account_id: uuid.UUID, amount: Decimal, description: str = "") -> Line:
    return Line(account_id, "C", amount, description)


_system_ids: dict[tuple[str, str], uuid.UUID] = {}


def system_account_id(db: Session, code: str) -> uuid.UUID:
    """Id of a system account. Ids are created once by the migration and never change, so they are cached
    per database to save a query on every money movement."""
    bind = db.get_bind()
    cache_key = (str(bind.engine.url), code)
    if cache_key not in _system_ids:
        account_id = db.scalar(select(LedgerAccount.id).where(LedgerAccount.code == code))
        if account_id is None:
            raise AppError(f"System account {code} is missing; run the database migrations", code="ledger_not_ready")
        _system_ids[cache_key] = account_id
    return _system_ids[cache_key]


def ensure_user_accounts(db: Session, user_id: uuid.UUID) -> None:
    """Create the user's wallet and receivable accounts if they do not exist yet (safe to call repeatedly)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    rows = [
        {
            "id": uuid.uuid4(),
            "code": f"USR:{user_id}:{purpose.upper()}",
            "name": name,
            "kind": kind,
            "purpose": purpose,
            "owner_id": user_id,
            "balance": ZERO,
            "allow_negative": False,
            "currency": "PGK",
        }
        for purpose, kind, name in USER_ACCOUNTS
    ]
    db.execute(pg_insert(LedgerAccount).values(rows).on_conflict_do_nothing(index_elements=["code"]))


def user_account(db: Session, user_id: uuid.UUID, purpose: str, *, lock: bool = False) -> LedgerAccount:
    stmt = select(LedgerAccount).where(LedgerAccount.owner_id == user_id, LedgerAccount.purpose == purpose)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    account = db.scalars(stmt).first()
    if account is None:  # older users created before their accounts existed: create on first use
        ensure_user_accounts(db, user_id)
        account = db.scalars(stmt).one()
    return account


def post_entry(
    db: Session,
    kind: str,
    lines: Iterable[Line],
    *,
    order_id: uuid.UUID | None = None,
    memo: str = "",
    created_by: uuid.UUID | None = None,
) -> JournalEntry:
    """Write one balanced journal entry and update the cached balances. Zero-amount lines are dropped."""
    lines = [line for line in lines if line.amount != ZERO]
    _validate(lines)

    accounts = _lock_accounts(db, {line.account_id for line in lines})
    new_balances = {account_id: account.balance for account_id, account in accounts.items()}
    for line in lines:
        normal = NORMAL_SIDE[accounts[line.account_id].kind]
        new_balances[line.account_id] += line.amount if normal == line.side else -line.amount
    for account_id, balance in new_balances.items():
        account = accounts[account_id]
        if balance < ZERO and not account.allow_negative:
            raise InsufficientFunds(_shortfall_message(account, balance))
    for account_id, balance in new_balances.items():
        accounts[account_id].balance = balance

    now = clock.now()
    entry = JournalEntry(
        id=uuid.uuid4(), kind=kind, order_id=order_id, memo=memo, created_by=created_by, created_at=now
    )
    db.add(entry)
    db.flush()
    db.execute(
        insert(Posting),
        [
            {
                "entry_id": entry.id,
                "account_id": line.account_id,
                "side": line.side,
                "amount": line.amount,
                "description": line.description,
                "created_at": now,
            }
            for line in lines
        ],
    )
    db.flush()
    return entry


def _validate(lines: Sequence[Line]) -> None:
    if len(lines) < 2:
        raise AppError("A journal entry needs at least two lines", code="ledger_invalid")
    for line in lines:
        if line.amount < ZERO or not is_cents(line.amount):
            raise AppError(f"Invalid posting amount {line.amount}", code="ledger_invalid")
    debits = sum((line.amount for line in lines if line.side == "D"), ZERO)
    credits = sum((line.amount for line in lines if line.side == "C"), ZERO)
    if debits != credits:
        raise AppError(f"Unbalanced entry: debits {debits} != credits {credits}", code="ledger_invalid")


def _lock_accounts(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, LedgerAccount]:
    # Lock in a fixed order (by id) so two transactions touching the same accounts cannot deadlock.
    stmt = (
        select(LedgerAccount)
        .where(LedgerAccount.id.in_(ids))
        .order_by(LedgerAccount.id)
        .with_for_update()
        .execution_options(populate_existing=True)  # read the locked row, not a stale cached copy
    )
    accounts = {account.id: account for account in db.scalars(stmt)}
    missing = ids - accounts.keys()
    if missing:
        raise AppError(f"Unknown ledger account(s): {sorted(map(str, missing))}", code="ledger_invalid")
    return accounts


def _shortfall_message(account: LedgerAccount, balance: Decimal) -> str:
    if account.purpose == "wallet":
        return f"Not enough Stars: this needs K{-balance} more"
    return f"Account {account.code} cannot go below zero"


# ---------- reports ----------


def order_escrow_balance(db: Session, order_id: uuid.UUID) -> Decimal:
    """Stars still held in escrow for one order (credits - debits on the escrow account for that order)."""
    escrow_id = system_account_id(db, ESCROW)
    signed = case((Posting.side == "C", Posting.amount), else_=-Posting.amount)
    value = db.scalar(
        select(func.coalesce(func.sum(signed), 0))
        .join(JournalEntry, JournalEntry.id == Posting.entry_id)
        .where(Posting.account_id == escrow_id, JournalEntry.order_id == order_id)
    )
    return Decimal(value or 0)


def trial_balance(db: Session) -> dict[str, Decimal]:
    """Total balance per account kind. Assets + expenses must equal liabilities + revenue + equity."""
    rows = db.execute(select(LedgerAccount.kind, func.sum(LedgerAccount.balance)).group_by(LedgerAccount.kind))
    totals = {kind: ZERO for kind in NORMAL_SIDE}
    totals.update({kind: Decimal(total) for kind, total in rows})
    return totals


def integrity_report(db: Session) -> dict[str, object]:
    """Re-derive every account balance from postings and check every entry balances."""
    signed = case((Posting.side == "D", Posting.amount), else_=-Posting.amount)
    derived: dict[uuid.UUID, Decimal] = {
        account_id: Decimal(total)
        for account_id, total in db.execute(select(Posting.account_id, func.sum(signed)).group_by(Posting.account_id))
    }
    mismatched = []
    for account in db.scalars(select(LedgerAccount)):
        net_debit = derived.get(account.id, ZERO)
        expected = net_debit if NORMAL_SIDE[account.kind] == "D" else -net_debit
        if expected != account.balance:
            mismatched.append({"code": account.code, "cached": str(account.balance), "from_postings": str(expected)})
    unbalanced = (
        db.execute(select(Posting.entry_id).group_by(Posting.entry_id).having(func.sum(signed) != 0)).scalars().all()
    )
    totals = trial_balance(db)
    left = totals["asset"] + totals["expense"]
    right = totals["liability"] + totals["revenue"] + totals["equity"]
    return {
        "ok": not mismatched and not unbalanced and left == right,
        "accounts_mismatched": mismatched,
        "entries_unbalanced": [str(e) for e in unbalanced],
        "assets_plus_expenses": str(left),
        "liabilities_plus_revenue_plus_equity": str(right),
    }


def trust_reconciliation(db: Session) -> dict[str, str]:
    """BPNG Directive 10.3-10.4, 12.1(c): customer money (wallets, escrow, pending withdrawals) must be fully
    covered by the trust bank account. A negative `safeguarding_position` means the operator must top up."""

    def total(purpose: str) -> Decimal:
        value = db.scalar(
            select(func.coalesce(func.sum(LedgerAccount.balance), 0)).where(LedgerAccount.purpose == purpose)
        )
        return Decimal(value or 0)

    trust = total("trust_bank")
    wallets, escrow, pending = total("wallet"), total("escrow"), total("withdrawals_pending")
    customer_funds = wallets + escrow + pending
    return {
        "trust_bank_per_ledger": str(trust),
        "customer_wallets": str(wallets),
        "escrow": str(escrow),
        "withdrawals_pending": str(pending),
        "customer_funds_total": str(customer_funds),
        "fee_revenue_not_yet_swept": str(total("fee_revenue")),
        "penalties_owed_by_sellers": str(total("receivable")),
        "safeguarding_position": str(trust - customer_funds),
    }

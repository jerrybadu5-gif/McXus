"""Stars wallet: balance, statement, deposits (maker-checker), sandbox top-up and withdrawals."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock, kyc
from app.config import get_settings
from app.errors import AppError, Conflict, Forbidden, LimitExceeded, NotFound
from app.ledger.service import (
    FEE_REVENUE,
    TRUST_BANK,
    WITHDRAWALS_PENDING,
    credit,
    debit,
    post_entry,
    system_account_id,
    user_account,
)
from app.models import Deposit, JournalEntry, Posting, User, Withdrawal

INFLOW_KINDS = ("deposit", "sandbox_topup")


def summary(db: Session, user: User) -> dict[str, object]:
    wallet = user_account(db, user.id, "wallet")
    receivable = user_account(db, user.id, "receivable")
    rules = kyc.TIERS[user.kyc_tier]
    return {
        "balance": wallet.balance,
        "penalties_owed": receivable.balance,
        "kyc_tier": user.kyc_tier,
        "kyc_tier_name": rules.name,
        "max_balance": rules.max_balance,
        "monthly_in_limit": rules.monthly_in,
        "monthly_in_used": monthly_inflow(db, user.id),
        "sandbox": get_settings().sandbox_mode,
    }


def statement(db: Session, user_id: uuid.UUID, limit: int = 50, offset: int = 0) -> list[dict[str, object]]:
    wallet = user_account(db, user_id, "wallet")
    rows = db.execute(
        select(Posting, JournalEntry.kind, JournalEntry.order_id)
        .join(JournalEntry, JournalEntry.id == Posting.entry_id)
        .where(Posting.account_id == wallet.id)
        .order_by(Posting.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "at": posting.created_at,
            "kind": kind,
            "order_id": order_id,
            "description": posting.description,
            # wallet is a liability: a credit adds Stars, a debit removes them
            "amount": posting.amount if posting.side == "C" else -posting.amount,
        }
        for posting, kind, order_id in rows
    ]


def monthly_inflow(db: Session, user_id: uuid.UUID) -> Decimal:
    wallet = user_account(db, user_id, "wallet")
    since = clock.start_of_png_month(clock.now())
    value = db.scalar(
        select(func.coalesce(func.sum(Posting.amount), 0))
        .join(JournalEntry, JournalEntry.id == Posting.entry_id)
        .where(
            Posting.account_id == wallet.id,
            Posting.side == "C",
            JournalEntry.kind.in_(INFLOW_KINDS),
            Posting.created_at >= since,
        )
    )
    return Decimal(value or 0)


def _check_inflow_limits(db: Session, user: User, amount: Decimal) -> None:
    rules = kyc.TIERS[user.kyc_tier]
    if user.kyc_tier == 0:
        raise Forbidden("Verify your account (level 1) before adding Stars", code="kyc_required")
    wallet = user_account(db, user.id, "wallet", lock=True)
    if rules.max_balance is not None and wallet.balance + amount > rules.max_balance:
        raise LimitExceeded(f"Your verification level allows a balance of up to K{rules.max_balance}")
    if rules.monthly_in is not None and monthly_inflow(db, user.id) + amount > rules.monthly_in:
        raise LimitExceeded(f"Your verification level allows K{rules.monthly_in} of deposits per month")


def sandbox_topup(db: Session, user: User, amount: Decimal) -> dict[str, object]:
    settings = get_settings()
    if not settings.sandbox_mode:
        raise Forbidden("Sandbox top-up is switched off")
    if amount > settings.sandbox_topup_max:
        raise LimitExceeded(f"Sandbox top-up is limited to K{settings.sandbox_topup_max} at a time")
    _check_inflow_limits(db, user, amount)
    wallet = user_account(db, user.id, "wallet")
    post_entry(
        db,
        "sandbox_topup",
        [
            debit(system_account_id(db, TRUST_BANK), amount, "Sandbox top-up (test Stars)"),
            credit(wallet.id, amount, "Sandbox top-up (test Stars)"),
        ],
        created_by=user.id,
    )
    return summary(db, user)


# ---------- deposits: recorded by one finance user, approved by another ----------


def record_deposit(
    db: Session, staff: User, user_id: uuid.UUID, amount: Decimal, method: str, external_ref: str
) -> Deposit:
    if db.get(User, user_id) is None:
        raise NotFound("Customer not found")
    if db.scalar(select(Deposit.id).where(Deposit.external_ref == external_ref)):
        raise Conflict(f"Bank reference {external_ref} has already been recorded", code="duplicate_reference")
    deposit = Deposit(
        id=uuid.uuid4(), user_id=user_id, amount=amount, method=method, external_ref=external_ref, created_by=staff.id
    )
    db.add(deposit)
    db.flush()
    return deposit


def decide_deposit(db: Session, staff: User, deposit_id: uuid.UUID, approve: bool) -> Deposit:
    deposit = db.scalars(select(Deposit).where(Deposit.id == deposit_id).with_for_update()).first()
    if deposit is None:
        raise NotFound("Deposit not found")
    if deposit.status != "pending":
        raise Conflict(f"Deposit is already {deposit.status}")
    if deposit.created_by == staff.id:
        raise Forbidden("A different finance officer must approve this deposit (maker-checker)", code="maker_checker")
    deposit.approved_by = staff.id
    deposit.decided_at = clock.now()
    if not approve:
        deposit.status = "rejected"
        return deposit
    customer = db.get(User, deposit.user_id)
    assert customer is not None
    _check_inflow_limits(db, customer, deposit.amount)
    wallet = user_account(db, customer.id, "wallet")
    description = f"Deposit ({deposit.method}) ref {deposit.external_ref}"
    entry = post_entry(
        db,
        "deposit",
        [
            debit(system_account_id(db, TRUST_BANK), deposit.amount, description),
            credit(wallet.id, deposit.amount, description),
        ],
        created_by=staff.id,
        memo=f"maker={deposit.created_by} checker={staff.id}",
    )
    deposit.status = "approved"
    deposit.entry_id = entry.id
    return deposit


# ---------- withdrawals ----------


def request_withdrawal(db: Session, user: User, amount: Decimal, bank_account: str) -> Withdrawal:
    kyc.require(user.kyc_tier, "withdraw")
    fee = get_settings().withdrawal_fee
    if amount <= fee:
        raise AppError(f"The amount must be more than the K{fee} withdrawal fee", code="amount_too_small")
    wallet = user_account(db, user.id, "wallet")
    withdrawal = Withdrawal(id=uuid.uuid4(), user_id=user.id, amount=amount, fee=fee, bank_account=bank_account)
    db.add(withdrawal)
    db.flush()
    post_entry(
        db,
        "withdrawal_request",
        [
            debit(wallet.id, amount, "Withdrawal to bank"),
            credit(system_account_id(db, WITHDRAWALS_PENDING), amount - fee, "Withdrawal to bank"),
            credit(system_account_id(db, FEE_REVENUE), fee, "Withdrawal fee"),
        ],
        created_by=user.id,
        memo=f"withdrawal={withdrawal.id}",
    )
    return withdrawal


def settle_withdrawal(
    db: Session, staff: User, withdrawal_id: uuid.UUID, paid: bool, bank_ref: str | None
) -> Withdrawal:
    withdrawal = db.scalars(select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update()).first()
    if withdrawal is None:
        raise NotFound("Withdrawal not found")
    if withdrawal.status != "requested":
        raise Conflict(f"Withdrawal is already {withdrawal.status}")
    net = withdrawal.amount - withdrawal.fee
    pending = system_account_id(db, WITHDRAWALS_PENDING)
    if paid:
        if not bank_ref:
            raise AppError("Enter the bank transfer reference", code="bank_ref_required")
        post_entry(
            db,
            "withdrawal_paid",
            [
                debit(pending, net, f"Paid out, bank ref {bank_ref}"),
                credit(system_account_id(db, TRUST_BANK), net, f"Paid out, bank ref {bank_ref}"),
            ],
            created_by=staff.id,
            memo=f"withdrawal={withdrawal.id}",
        )
        withdrawal.status = "paid"
    else:
        wallet = user_account(db, withdrawal.user_id, "wallet")
        post_entry(
            db,
            "withdrawal_rejected",
            [
                debit(pending, net, "Withdrawal rejected"),
                debit(system_account_id(db, FEE_REVENUE), withdrawal.fee, "Withdrawal fee refunded"),
                credit(wallet.id, withdrawal.amount, "Withdrawal rejected, Stars returned"),
            ],
            created_by=staff.id,
            memo=f"withdrawal={withdrawal.id}",
        )
        withdrawal.status = "rejected"
    withdrawal.bank_ref = bank_ref
    withdrawal.processed_by = staff.id
    withdrawal.processed_at = clock.now()
    return withdrawal

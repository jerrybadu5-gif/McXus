import threading
import uuid
from decimal import Decimal as D

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import get_sessionmaker
from app.errors import AppError, InsufficientFunds
from app.escrow import service as escrow
from app.ledger.service import (
    ESCROW,
    TRUST_BANK,
    credit,
    debit,
    integrity_report,
    post_entry,
    system_account_id,
    trust_reconciliation,
    user_account,
)
from tests.conftest import make_user


def test_unbalanced_entry_rejected_before_database(db):
    user = make_user(db)
    wallet = user_account(db, user.id, "wallet")
    with pytest.raises(AppError, match="Unbalanced"):
        post_entry(db, "test", [debit(system_account_id(db, TRUST_BANK), D("10.00")), credit(wallet.id, D("9.99"))])


def test_database_trigger_rejects_unbalanced_entry(db):
    """Even code that bypasses the service cannot commit an unbalanced entry."""
    user = make_user(db)
    wallet = user_account(db, user.id, "wallet")
    entry_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO journal_entries (id, kind, memo, created_at) VALUES (:id, 'hack', '', now())"),
        {"id": entry_id},
    )
    db.execute(
        text(
            "INSERT INTO postings (entry_id, account_id, side, amount, description, created_at) "
            "VALUES (:e, :a, 'C', 100, '', now())"
        ),
        {"e": entry_id, "a": wallet.id},
    )
    with pytest.raises(DBAPIError, match="unbalanced"):
        db.commit()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE postings SET amount = 1",
        "DELETE FROM postings",
        "UPDATE journal_entries SET memo = 'x'",
        "DELETE FROM order_events",
    ],
)
def test_financial_records_are_append_only(db, users, sql):
    escrow.pay(db, users["buyer"], escrow.create_order(db, users["buyer"], users["seller"].id, "x", D("5.00")).id)
    db.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text(sql))
    db.rollback()


def test_wallet_cannot_go_negative(db):
    user = make_user(db, stars=50)
    wallet = user_account(db, user.id, "wallet")
    with pytest.raises(InsufficientFunds, match="K10.00 more"):
        post_entry(db, "test", [debit(wallet.id, D("60.00")), credit(system_account_id(db, ESCROW), D("60.00"))])
    db.rollback()
    assert user_account(db, user.id, "wallet").balance == D("50.00")


def test_integrity_and_trust_reconciliation_after_topups(db):
    make_user(db, stars=100)
    make_user(db, stars=250)
    report = integrity_report(db)
    assert report["ok"], report
    recon = trust_reconciliation(db)
    assert recon["trust_bank_per_ledger"] == "350.00"
    assert recon["customer_funds_total"] == "350.00"
    assert recon["safeguarding_position"] == "0.00"


def test_concurrent_payments_cannot_overspend(db):
    """Two orders of K300 paid at the same moment from a K500 wallet: exactly one succeeds."""
    buyer = make_user(db, stars=500)
    seller = make_user(db)
    orders = [escrow.create_order(db, buyer, seller.id, f"item {i}", D("300.00")).id for i in range(2)]
    db.commit()
    results: list[str] = []
    barrier = threading.Barrier(2)

    def pay(order_id: uuid.UUID) -> None:
        with get_sessionmaker()() as session:
            me = session.get(type(buyer), buyer.id)
            barrier.wait()
            try:
                escrow.pay(session, me, order_id)
                session.commit()
                results.append("paid")
            except InsufficientFunds:
                session.rollback()
                results.append("insufficient")

    threads = [threading.Thread(target=pay, args=(oid,)) for oid in orders]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["insufficient", "paid"]
    db.expire_all()
    assert user_account(db, buyer.id, "wallet").balance == D("200.00")
    assert integrity_report(db)["ok"]

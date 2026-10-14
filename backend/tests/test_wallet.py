from decimal import Decimal as D

import pytest

from app.errors import AppError, Conflict, Forbidden, LimitExceeded
from app.escrow import service as escrow
from app.ledger.service import integrity_report, trust_reconciliation, user_account
from app.wallet import service as wallet
from tests.conftest import make_user


def bal(db, user):
    db.expire_all()
    return user_account(db, user.id, "wallet").balance


def test_tier1_balance_cap(db):
    user = make_user(db, tier=1, stars=900)
    with pytest.raises(LimitExceeded, match="K1000"):
        wallet.sandbox_topup(db, user, D("101.00"))


def test_tier1_monthly_inflow_cap(db, users, fake_clock):
    buyer = make_user(db, tier=1)
    for i in range(3):  # add K1000 and spend it, three times = K3000 this month
        wallet.sandbox_topup(db, buyer, D("1000.00"))
        order = escrow.create_order(db, buyer, users["seller"].id, f"item {i}", D("1000.00"))
        escrow.pay(db, buyer, order.id)
        db.commit()
    assert wallet.monthly_inflow(db, buyer.id) == D("3000.00")
    with pytest.raises(LimitExceeded, match="K3000 of deposits per month"):
        wallet.sandbox_topup(db, buyer, D("1.00"))
    db.rollback()
    fake_clock.advance(days=31)  # next month (PNG time)
    wallet.sandbox_topup(db, buyer, D("1.00"))


def test_tier0_cannot_add_stars(db):
    user = make_user(db, tier=0)
    with pytest.raises(Forbidden, match="level 1"):
        wallet.sandbox_topup(db, user, D("10.00"))


def test_deposit_needs_a_second_finance_officer(db, users):
    customer = users["buyer"]
    dep = wallet.record_deposit(db, users["finance_a"], customer.id, D("250.00"), "bank_transfer", "BSP-TXN-001")
    db.commit()
    with pytest.raises(Forbidden, match="maker-checker"):
        wallet.decide_deposit(db, users["finance_a"], dep.id, approve=True)
    db.rollback()
    wallet.decide_deposit(db, users["finance_b"], dep.id, approve=True)
    db.commit()
    assert bal(db, customer) == D("750.00")
    with pytest.raises(Conflict, match="already approved"):
        wallet.decide_deposit(db, users["finance_b"], dep.id, approve=True)


def test_duplicate_bank_reference_is_refused(db, users):
    wallet.record_deposit(db, users["finance_a"], users["buyer"].id, D("10.00"), "bank_transfer", "REF-1")
    db.commit()
    with pytest.raises(Conflict, match="already been recorded"):
        wallet.record_deposit(db, users["finance_a"], users["buyer"].id, D("10.00"), "bank_transfer", "REF-1")


def test_withdrawal_paid(db, users):
    customer = users["buyer"]
    w = wallet.request_withdrawal(db, customer, D("100.00"), "BSP 1001234567")
    db.commit()
    assert bal(db, customer) == D("400.00")
    with pytest.raises(AppError, match="bank transfer reference"):
        wallet.settle_withdrawal(db, users["finance_a"], w.id, paid=True, bank_ref=None)
    wallet.settle_withdrawal(db, users["finance_a"], w.id, paid=True, bank_ref="BSP-OUT-9")
    db.commit()
    recon = trust_reconciliation(db)
    assert recon["trust_bank_per_ledger"] == "402.00"  # 500 in, 98 paid out
    assert recon["customer_funds_total"] == "400.00"
    assert integrity_report(db)["ok"]


def test_withdrawal_rejected_returns_everything(db, users):
    customer = users["buyer"]
    w = wallet.request_withdrawal(db, customer, D("100.00"), "BSP 1001234567")
    wallet.settle_withdrawal(db, users["finance_a"], w.id, paid=False, bank_ref=None)
    db.commit()
    assert bal(db, customer) == D("500.00")
    assert integrity_report(db)["ok"]


def test_withdrawal_rules(db, users):
    basic = make_user(db, tier=1, stars=100)
    with pytest.raises(Forbidden, match="level 2"):
        wallet.request_withdrawal(db, basic, D("50.00"), "BSP 1")
    with pytest.raises(AppError, match="more than the K2.00"):
        wallet.request_withdrawal(db, users["buyer"], D("2.00"), "BSP 1")

"""Escrow lifecycle. Default settings: escrow fee 3% (min K1), cancel fee 5% (min K2) split 50/50,
seller must accept within 20 minutes, auto-release 7 days after dispatch."""

from decimal import Decimal as D

import pytest

from app.errors import AppError, Conflict, Forbidden, InsufficientFunds
from app.escrow import service as escrow
from app.jobs import run_timers
from app.ledger.service import FEE_REVENUE, integrity_report, system_account_id, trust_reconciliation
from app.models import LedgerAccount, OrderEvent
from tests.conftest import make_user


def balance(db, user, purpose="wallet"):
    db.expire_all()
    acct = db.query(LedgerAccount).filter_by(owner_id=user.id, purpose=purpose).one()
    return acct.balance


def revenue(db):
    db.expire_all()
    return db.get(LedgerAccount, system_account_id(db, FEE_REVENUE)).balance


def paid_order(db, users, amount="200.00"):
    order = escrow.create_order(db, users["buyer"], users["seller"].id, "Solar lamp", D(amount))
    order, pin = escrow.pay(db, users["buyer"], order.id)
    db.commit()
    return order, pin


def assert_books_ok(db):
    report = integrity_report(db)
    assert report["ok"], report


def test_happy_path_with_handover_pin(db, users):
    order, pin = paid_order(db, users)
    assert order.status == "FUNDED"
    assert balance(db, users["buyer"]) == D("300.00")
    escrow.accept(db, users["seller"], order.id)
    escrow.dispatch(db, users["seller"], order.id)
    escrow.handover(db, users["seller"], order.id, pin)
    db.commit()
    assert order.status == "RELEASED"
    assert balance(db, users["seller"]) == D("194.00")  # 200 - 3% escrow fee
    assert revenue(db) == D("6.00")
    assert (order.seller_paid, order.fee_charged) == (D("194.00"), D("6.00"))
    assert_books_ok(db)
    recon = trust_reconciliation(db)
    assert recon["safeguarding_position"] == "6.00"  # trust holds customer funds plus earned fees


def test_meet_up_handover_straight_after_accept(db, users):
    order, pin = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    escrow.handover(db, users["seller"], order.id, pin)
    db.commit()
    assert order.status == "RELEASED"


def test_buyer_can_confirm_receipt(db, users):
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    escrow.dispatch(db, users["seller"], order.id)
    escrow.confirm_receipt(db, users["buyer"], order.id)
    db.commit()
    assert order.status == "RELEASED"
    assert balance(db, users["seller"]) == D("194.00")


def test_wrong_pins_lock_handover_until_buyer_reissues(db, users):
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    db.commit()
    for _ in range(5):
        with pytest.raises(AppError, match="Wrong PIN"):
            escrow.handover(db, users["seller"], order.id, "000000" if _ % 2 else "111111")
    with pytest.raises(Conflict, match="Too many wrong PINs"):
        escrow.handover(db, users["seller"], order.id, "123456")
    new_pin = escrow.reissue_pin(db, users["buyer"], order.id)
    db.commit()
    escrow.handover(db, users["seller"], order.id, new_pin)
    db.commit()
    assert order.status == "RELEASED"


def test_only_the_seller_can_enter_the_pin(db, users):
    order, pin = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    with pytest.raises(Forbidden):
        escrow.handover(db, users["buyer"], order.id, pin)


def test_buyer_cancel_before_payment_is_free(db, users):
    order = escrow.create_order(db, users["buyer"], users["seller"].id, "Phone", D("200.00"))
    escrow.cancel(db, users["buyer"], order.id, "changed mind")
    db.commit()
    assert order.status == "CANCELLED"
    assert balance(db, users["buyer"]) == D("500.00")


@pytest.mark.parametrize("accept_first", [False, True])
def test_buyer_cancel_after_payment_pays_fee_shared_with_seller(db, users, accept_first):
    order, _ = paid_order(db, users)
    if accept_first:
        escrow.accept(db, users["seller"], order.id)
    escrow.cancel(db, users["buyer"], order.id, "found cheaper")
    db.commit()
    assert order.status == "CANCELLED"
    assert balance(db, users["buyer"]) == D("490.00")  # 200 refunded less K10 fee
    assert balance(db, users["seller"]) == D("5.00")  # half the fee
    assert revenue(db) == D("5.00")
    assert_books_ok(db)


def test_no_buyer_cancel_after_dispatch(db, users):
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    escrow.dispatch(db, users["seller"], order.id)
    with pytest.raises(Conflict, match="Open a dispute"):
        escrow.cancel(db, users["buyer"], order.id, "")


def test_auto_reject_after_20_minutes_seller_owes_fee(db, users, fake_clock):
    order, _ = paid_order(db, users)
    fake_clock.advance(minutes=19, seconds=59)
    assert run_timers() == {}
    fake_clock.advance(seconds=1)
    assert run_timers() == {"AUTO_REJECTED": 1}
    db.expire_all()
    order = escrow.get_order(db, order.id)
    assert order.status == "AUTO_REJECTED"
    assert balance(db, users["buyer"]) == D("505.00")  # full refund + K5 compensation
    assert balance(db, users["seller"]) == D("0.00")
    assert balance(db, users["seller"], "receivable") == D("10.00")  # seller owes the K10 fee
    assert revenue(db) == D("5.00")
    assert_books_ok(db)


def test_owed_penalty_is_taken_from_the_sellers_next_sale(db, users, fake_clock):
    order, _ = paid_order(db, users)
    fake_clock.advance(minutes=21)
    run_timers()
    order2, pin2 = paid_order(db, users, "100.00")
    escrow.accept(db, users["seller"], order2.id)
    escrow.handover(db, users["seller"], order2.id, pin2)
    db.commit()
    assert balance(db, users["seller"]) == D("87.00")  # 100 - K3 escrow fee - K10 owed
    assert balance(db, users["seller"], "receivable") == D("0.00")
    assert order2.seller_paid == D("87.00")
    assert_books_ok(db)


def test_seller_reject_pays_what_wallet_allows_and_owes_the_rest(db, users):
    seller = users["seller"]
    first, pin = paid_order(db, users, "4.00")  # K4 sale -> seller nets K3 (min fee K1)
    escrow.accept(db, seller, first.id)
    escrow.handover(db, seller, first.id, pin)
    db.commit()
    assert balance(db, seller) == D("3.00")
    order, _ = paid_order(db, users)
    escrow.reject(db, seller, order.id, "out of stock")
    db.commit()
    assert order.status == "SELLER_REJECTED"
    assert balance(db, seller) == D("0.00")
    assert balance(db, seller, "receivable") == D("7.00")  # K10 fee: K3 paid now, K7 owed
    assert_books_ok(db)


def test_seller_cancel_after_accept_is_penalised(db, users):
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    escrow.cancel(db, users["seller"], order.id, "")
    db.commit()
    assert order.status == "SELLER_CANCELLED"
    assert balance(db, users["buyer"]) == D("505.00")


def test_accept_after_window_is_refused(db, users, fake_clock):
    order, _ = paid_order(db, users)
    fake_clock.advance(minutes=20)
    with pytest.raises(Conflict, match="acceptance window"):
        escrow.accept(db, users["seller"], order.id)


def test_auto_release_seven_days_after_dispatch(db, users, fake_clock):
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    escrow.dispatch(db, users["seller"], order.id)
    db.commit()
    fake_clock.advance(days=6, hours=23)
    assert run_timers() == {}
    fake_clock.advance(hours=1)
    assert run_timers() == {"RELEASED": 1}
    assert balance(db, users["seller"]) == D("194.00")


def test_dispute_freezes_auto_release_and_mediator_splits(db, users, fake_clock):
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    escrow.dispatch(db, users["seller"], order.id)
    escrow.open_dispute(db, users["buyer"], order.id, "Lamp arrived cracked")
    db.commit()
    fake_clock.advance(days=8)
    assert run_timers() == {}  # disputed orders are never auto-released
    with pytest.raises(Forbidden):
        escrow.resolve_dispute(db, users["buyer"], order.id, D("200.00"), "I win")
    escrow.resolve_dispute(db, users["mediator"], order.id, D("50.00"), "Partial damage: 25% refund")
    db.commit()
    assert order.status == "RESOLVED"
    assert balance(db, users["buyer"]) == D("350.00")  # 300 + 50 refund
    assert balance(db, users["seller"]) == D("145.50")  # 150 - 3% (4.50)
    assert_books_ok(db)


def test_full_refund_dispute_charges_seller_no_escrow_fee(db, users):
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    escrow.open_dispute(db, users["seller"], order.id, "Buyer never turned up")
    escrow.resolve_dispute(db, users["mediator"], order.id, D("200.00"), "Refund in full")
    db.commit()
    assert balance(db, users["buyer"]) == D("500.00")
    assert revenue(db) == D("0.00")


def test_kyc_rules(db, users):
    unverified = make_user(db, tier=0)
    with pytest.raises(Forbidden, match="verification level 1"):
        escrow.create_order(db, unverified, users["seller"].id, "x", D("10.00"))
    basic_seller = make_user(db, tier=1)
    with pytest.raises(Conflict, match="not verified to sell"):
        escrow.create_order(db, users["buyer"], basic_seller.id, "x", D("10.00"))


def test_insufficient_funds_leaves_order_unpaid(db, users):
    order = escrow.create_order(db, users["buyer"], users["seller"].id, "TV", D("900.00"))
    db.commit()
    with pytest.raises(InsufficientFunds):
        escrow.pay(db, users["buyer"], order.id)
    db.rollback()
    assert escrow.get_order(db, order.id).status == "CREATED"


def test_invalid_transitions_are_refused(db, users):
    order, pin = paid_order(db, users)
    with pytest.raises(Conflict):
        escrow.dispatch(db, users["seller"], order.id)  # not accepted yet
    with pytest.raises(Conflict):
        escrow.pay(db, users["buyer"], order.id)  # already paid
    with pytest.raises(Conflict):
        escrow.open_dispute(db, users["buyer"], order.id, "too early")


def test_every_step_is_logged(db, users):
    order, pin = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    escrow.handover(db, users["seller"], order.id, pin)
    db.commit()
    steps = [
        (e.from_status, e.to_status) for e in db.query(OrderEvent).filter_by(order_id=order.id).order_by(OrderEvent.id)
    ]
    assert steps == [(None, "CREATED"), ("CREATED", "FUNDED"), ("FUNDED", "ACCEPTED"), ("ACCEPTED", "RELEASED")]

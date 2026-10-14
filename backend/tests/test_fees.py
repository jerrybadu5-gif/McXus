from decimal import Decimal as D

from app.config import Settings
from app.escrow.fees import cancel_fee, escrow_fee, split_cancel_fee

S = Settings()


def test_escrow_fee_is_three_percent():
    assert escrow_fee(D("200.00"), S) == D("6.00")
    assert escrow_fee(D("99.99"), S) == D("3.00")  # 2.9997 rounds half-up to 3.00


def test_escrow_fee_minimum_and_cap():
    assert escrow_fee(D("10.00"), S) == D("1.00")  # 0.30 -> minimum K1
    assert escrow_fee(D("20000.00"), S) == D("150.00")  # 600 -> capped at K150


def test_escrow_fee_never_exceeds_amount_and_zero_for_nothing():
    assert escrow_fee(D("0.50"), S) == D("0.50")
    assert escrow_fee(D("0.00"), S) == D("0.00")


def test_cancel_fee_five_percent_with_minimum():
    assert cancel_fee(D("200.00"), S) == D("10.00")
    assert cancel_fee(D("20.00"), S) == D("2.00")  # 1.00 -> minimum K2
    assert cancel_fee(D("1.50"), S) == D("1.50")  # never more than the order


def test_cancel_fee_split_adds_up():
    for fee in (D("10.00"), D("2.00"), D("0.01"), D("7.33")):
        split = split_cancel_fee(fee, S)
        assert split.counterparty + split.platform == fee
    assert split_cancel_fee(D("10.00"), S).counterparty == D("5.00")

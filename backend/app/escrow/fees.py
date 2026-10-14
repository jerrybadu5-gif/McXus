"""Fee rules (pure functions, all values from Settings)."""

from dataclasses import dataclass
from decimal import Decimal

from app.config import Settings
from app.money import ZERO, q


def escrow_fee(amount: Decimal, s: Settings) -> Decimal:
    """Seller pays on release: rate, clamped to [min, max], never more than the amount itself."""
    if amount <= ZERO:
        return ZERO
    fee = min(max(q(amount * s.escrow_fee_rate), s.escrow_fee_min), s.escrow_fee_max)
    return min(fee, amount)


def cancel_fee(amount: Decimal, s: Settings) -> Decimal:
    """Charged to whoever cancels after payment: rate with a minimum, never more than the order."""
    return min(max(q(amount * s.cancel_fee_rate), s.cancel_fee_min), amount)


@dataclass(frozen=True)
class FeeSplit:
    counterparty: Decimal  # compensation to the other side of the order
    platform: Decimal


def split_cancel_fee(fee: Decimal, s: Settings) -> FeeSplit:
    counterparty = q(fee * s.cancel_fee_counterparty_share)
    return FeeSplit(counterparty=counterparty, platform=fee - counterparty)

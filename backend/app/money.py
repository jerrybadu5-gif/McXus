"""Money helpers. Amounts are Decimal with 2 places; never float."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def q(value: Decimal) -> Decimal:
    """Round to the cent, half up (the convention for PGK)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def is_cents(value: Decimal) -> bool:
    return value == value.quantize(CENT)

"""KYC tiers and wallet limits (placeholders agreed in Round 2; tune with the partner issuer and FASU)."""

from dataclasses import dataclass
from decimal import Decimal

from app.errors import Forbidden


@dataclass(frozen=True)
class TierRules:
    name: str
    can_buy: bool
    can_sell: bool
    can_withdraw: bool
    max_balance: Decimal | None  # None = set per agreement (registered sellers)
    monthly_in: Decimal | None


TIERS: dict[int, TierRules] = {
    0: TierRules("Chat only", False, False, False, Decimal("0"), Decimal("0")),
    1: TierRules("Basic", True, False, False, Decimal("1000"), Decimal("3000")),
    2: TierRules("Verified", True, True, True, Decimal("10000"), Decimal("30000")),
    3: TierRules("Registered seller", True, True, True, None, None),
}


def _allows(rules: TierRules, action: str) -> bool:
    return {"buy": rules.can_buy, "sell": rules.can_sell, "withdraw": rules.can_withdraw}[action]


def require(tier: int, action: str) -> TierRules:
    """Return the tier's rules, or raise Forbidden naming the lowest tier that allows `action`."""
    rules = TIERS[tier]
    if not _allows(rules, action):
        needed = next(t for t, r in TIERS.items() if _allows(r, action))
        raise Forbidden(
            f"Your account needs verification level {needed} ({TIERS[needed].name}) to {action}", code="kyc_required"
        )
    return rules

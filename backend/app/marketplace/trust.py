"""Seller trust score v1 (requirements §7): built from what sellers actually do, computed on read.

score (0-100) =
    55 x rating      (Bayesian average, prior 3.5 stars weighted as 5 reviews, scaled 1-5 -> 0-1)
  + 25 x track record (completed sales, full credit at 50)
  + 10 if verified (tier 2+) + 10 more if registered business (tier 3)
  - 10 per dispute lost (buyer got money back) - 5 per late seller cancellation
Shown publicly as a badge; the raw score is for staff only.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Order, Review, User

PRIOR_STARS = Decimal("3.5")
PRIOR_WEIGHT = 5
FULL_TRACK_RECORD = 50


@dataclass(frozen=True)
class Trust:
    score: int
    badge: str
    rating: Decimal | None  # plain average, for display
    reviews: int
    completed_sales: int
    disputes_lost: int
    late_cancellations: int


def _badge(score: int, tier: int, completed: int) -> str:
    if tier >= 3 and score >= 60:
        return "verified_store"
    if completed < 3:
        return "new_seller"
    if score >= 80:
        return "gold"
    if score >= 60:
        return "silver"
    if score >= 40:
        return "bronze"
    return "caution"


def for_sellers(db: Session, seller_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Trust]:
    """Trust for many sellers in three queries (used by listing search results)."""
    ids = list(set(seller_ids))
    if not ids:
        return {}
    tiers = dict(db.execute(select(User.id, User.kyc_tier).where(User.id.in_(ids))).all())
    ratings = {
        seller: (int(count), Decimal(total or 0))
        for seller, count, total in db.execute(
            select(Review.seller_id, func.count(), func.sum(Review.stars))
            .where(Review.seller_id.in_(ids))
            .group_by(Review.seller_id)
        )
    }
    counts = {
        row.seller_id: row
        for row in db.execute(
            select(
                Order.seller_id,
                func.count().filter(Order.status == "RELEASED").label("completed"),
                func.count().filter(and_(Order.status == "RESOLVED", Order.buyer_refunded > 0)).label("lost"),
                func.count().filter(and_(Order.status == "SELLER_CANCELLED", Order.fee_charged > 0)).label("late"),
            )
            .where(Order.seller_id.in_(ids))
            .group_by(Order.seller_id)
        )
    }
    result = {}
    for seller in ids:
        n, total = ratings.get(seller, (0, Decimal(0)))
        row = counts.get(seller)
        completed, lost, late = (row.completed, row.lost, row.late) if row else (0, 0, 0)
        tier = tiers.get(seller, 0)
        bayes = (PRIOR_STARS * PRIOR_WEIGHT + total) / (PRIOR_WEIGHT + n)
        raw = (
            55 * float((bayes - 1) / 4)
            + 25 * min(completed, FULL_TRACK_RECORD) / FULL_TRACK_RECORD
            + (10 if tier >= 2 else 0)
            + (10 if tier >= 3 else 0)
            - 10 * lost
            - 5 * late
        )
        score = max(0, min(100, round(raw)))
        result[seller] = Trust(
            score=score,
            badge=_badge(score, tier, completed),
            rating=(total / n).quantize(Decimal("0.1")) if n else None,
            reviews=n,
            completed_sales=completed,
            disputes_lost=lost,
            late_cancellations=late,
        )
    return result


def for_seller(db: Session, seller_id: uuid.UUID) -> Trust:
    return for_sellers(db, [seller_id])[seller_id]

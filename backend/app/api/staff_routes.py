"""Staff console API (M4): user search and profile, freezing accounts, order lookup, the overview counts and the
audit trail. Money and dispute actions are in routes.py and dispute_routes.py; moderation in market_routes.py."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import audit
from app.api.schemas import OrderOut, UserOut
from app.auth.deps import require_role
from app.db import get_db
from app.disputes import service as disputes
from app.errors import AppError, NotFound
from app.ledger.service import user_account
from app.marketplace import trust
from app.models import Deposit, Dispute, ListingReport, Order, StaffAction, User, Withdrawal

router = APIRouter(prefix="/v1/admin", tags=["staff"])
DB = Annotated[Session, Depends(get_db)]
AnyStaff = Annotated[User, Depends(require_role("support", "kyc", "moderator", "mediator", "finance", "compliance"))]
Oversight = Annotated[User, Depends(require_role("compliance"))]
Page = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
STAFF_ROLES = ("support", "kyc", "moderator", "mediator", "finance", "compliance", "admin")


class UserProfileOut(BaseModel):
    user: UserOut
    created_at: datetime
    wallet: Decimal
    penalties_owed: Decimal
    orders_as_buyer: int
    orders_as_seller: int
    disputes: int
    trust_badge: str
    trust_score: int
    completed_sales: int


class StatusIn(BaseModel):
    status: Literal["active", "frozen"]
    reason: str = Field(min_length=5, max_length=500)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: uuid.UUID
    actor: str = ""
    action: str
    target_type: str
    target_id: str
    detail: str
    created_at: datetime


class OverviewOut(BaseModel):
    role: str
    disputes: dict[str, int]
    disputes_overdue: int
    deposits_pending: int
    withdrawals_requested: int
    reports_open: int
    users: int
    staff: int


@router.get("/overview")
def overview(staff: AnyStaff, db: DB) -> OverviewOut:
    """Counts for the console's home page (what is waiting for whom)."""
    queue = disputes.queue(db, staff, "mediation", False, 500, 0)

    def count(stmt: object) -> int:
        return db.scalar(stmt) or 0  # type: ignore[call-overload]

    return OverviewOut(
        role=staff.role,
        disputes=disputes.counts(db),
        disputes_overdue=sum(1 for d in queue if d["overdue"]),
        deposits_pending=count(select(func.count()).select_from(Deposit).where(Deposit.status == "pending")),
        withdrawals_requested=count(
            select(func.count()).select_from(Withdrawal).where(Withdrawal.status == "requested")
        ),
        reports_open=count(select(func.count()).select_from(ListingReport).where(ListingReport.status == "open")),
        users=count(select(func.count()).select_from(User)),
        staff=count(select(func.count()).select_from(User).where(User.role.in_(STAFF_ROLES))),
    )


@router.get("/users")
def search_users(
    staff: AnyStaff, db: DB, q: str = "", role: str | None = None, limit: Page = 50, offset: Offset = 0
) -> list[UserOut]:
    """Find people by phone, name or id. Use role=staff for all staff accounts."""
    stmt = select(User)
    q = q.strip()
    if q:
        try:
            stmt = stmt.where(User.id == uuid.UUID(q))
        except ValueError:
            digits = "".join(ch for ch in q if ch.isdigit())
            conditions = [User.display_name.ilike(f"%{q}%")]
            if len(digits) >= 3:
                conditions.append(User.phone.like(f"%{digits}%"))
            stmt = stmt.where(or_(*conditions))
    if role == "staff":
        stmt = stmt.where(User.role.in_(STAFF_ROLES))
    elif role:
        stmt = stmt.where(User.role == role)
    rows = db.scalars(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))
    return [UserOut.model_validate(u) for u in rows]


@router.get("/users/names")
def user_names(staff: AnyStaff, db: DB, ids: Annotated[list[uuid.UUID], Query(max_length=200)]) -> dict[str, str]:
    """Display names (or phone) for ids shown in staff lists."""
    rows = db.scalars(select(User).where(User.id.in_(ids)))
    return {str(u.id): u.display_name or u.phone or "McXus user" for u in rows}


@router.get("/users/{user_id}")
def user_profile(user_id: uuid.UUID, staff: AnyStaff, db: DB) -> UserProfileOut:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User not found")

    def count(*where: object) -> int:
        return db.scalar(select(func.count()).select_from(Order).where(*where)) or 0  # type: ignore[arg-type]

    t = trust.for_seller(db, user.id)
    disputes_count = (
        db.scalar(
            select(func.count())
            .select_from(Dispute)
            .join(Order, Order.id == Dispute.order_id)
            .where(or_(Order.buyer_id == user.id, Order.seller_id == user.id))
        )
        or 0
    )
    return UserProfileOut(
        user=UserOut.model_validate(user),
        created_at=user.created_at,
        wallet=user_account(db, user.id, "wallet").balance,
        penalties_owed=user_account(db, user.id, "receivable").balance,
        orders_as_buyer=count(Order.buyer_id == user.id),
        orders_as_seller=count(Order.seller_id == user.id),
        disputes=disputes_count,
        trust_badge=t.badge,
        trust_score=t.score,
        completed_sales=t.completed_sales,
    )


@router.post("/users/{user_id}/status")
def set_status(user_id: uuid.UUID, body: StatusIn, staff: Oversight, db: DB) -> UserOut:
    """Freeze an account (it cannot sign in or move Stars) or unfreeze it. Compliance or admin; logged."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    if user.id == staff.id:
        raise AppError("You cannot change your own account status", code="own_account")
    user.status = body.status
    audit.record(db, staff, f"user_{body.status}", "user", user.id, body.reason)
    db.commit()
    return UserOut.model_validate(user)


@router.get("/orders")
def search_orders(
    staff: AnyStaff,
    db: DB,
    status: str | None = None,
    user_id: uuid.UUID | None = None,
    q: str = "",
    limit: Page = 50,
    offset: Offset = 0,
) -> list[OrderOut]:
    """Orders by status, by person (as buyer or seller), by title or by id."""
    stmt = select(Order)
    if status:
        stmt = stmt.where(Order.status == status)
    if user_id:
        stmt = stmt.where(or_(Order.buyer_id == user_id, Order.seller_id == user_id))
    q = q.strip()
    if q:
        try:
            stmt = stmt.where(Order.id == uuid.UUID(q))
        except ValueError:
            stmt = stmt.where(Order.title.ilike(f"%{q}%"))
    rows = db.scalars(stmt.order_by(Order.created_at.desc()).limit(limit).offset(offset))
    return [OrderOut.model_validate(o) for o in rows]


@router.get("/audit")
def audit_log(
    staff: Oversight, db: DB, target_id: str | None = None, limit: Page = 100, offset: Offset = 0
) -> list[AuditOut]:
    """What staff did, newest first (compliance and admin)."""
    stmt = select(StaffAction)
    if target_id:
        stmt = stmt.where(StaffAction.target_id == target_id)
    rows = list(db.scalars(stmt.order_by(StaffAction.id.desc()).limit(limit).offset(offset)))
    names = {
        u.id: u.display_name or u.phone or "staff"
        for u in db.scalars(select(User).where(User.id.in_({r.actor_id for r in rows})))
    }
    return [AuditOut.model_validate(r).model_copy(update={"actor": names.get(r.actor_id, "")}) for r in rows]

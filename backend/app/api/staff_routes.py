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

from app import freezes, people
from app.api.schemas import OrderOut, UserOut
from app.auth.deps import require_role
from app.db import get_db
from app.disputes import service as disputes
from app.errors import NotFound
from app.ledger.service import user_account
from app.marketplace import trust
from app.models import AccountFreeze, Deposit, Dispute, ListingReport, Order, StaffAction, User, Withdrawal
from app.social import service as social

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
    content_reports_open: int
    freezes_open: int
    freeze_appeals: int
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
        content_reports_open=social.open_report_count(db),
        freezes_open=count(
            select(func.count()).select_from(AccountFreeze).where(AccountFreeze.status.in_(freezes.OPEN))
        ),
        freeze_appeals=count(select(func.count()).select_from(AccountFreeze).where(AccountFreeze.status == "appealed")),
        users=count(select(func.count()).select_from(User)),
        staff=count(select(func.count()).select_from(User).where(User.role.in_(STAFF_ROLES))),
    )


@router.get("/users")
def search_users(
    staff: AnyStaff, db: DB, q: str = "", role: str | None = None, limit: Page = 50, offset: Offset = 0
) -> list[UserOut]:
    """Find people by name (any case, words in any order), phone digits or id. role=staff lists staff."""
    stmt = select(User)
    condition = people.match(q)
    if condition is not None:
        stmt = stmt.where(condition)
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
    user = db.get(User, user_id, with_for_update=True)
    if user is None:
        raise NotFound("User not found")
    if body.status == "frozen":
        freezes.freeze(db, staff, user, body.reason)
    else:
        freezes.unfreeze(db, staff, user, body.reason)
    db.commit()
    return UserOut.model_validate(user)


class FreezeCaseOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user: dict[str, object]
    status: Literal["frozen", "appealed", "unfrozen", "upheld"]
    reason: str
    frozen_at: datetime
    frozen_by: str | None
    frozen_by_id: uuid.UUID | None
    appeal_text: str
    appealed_at: datetime | None
    decision_note: str
    decided_at: datetime | None
    decided_by: str | None


class FreezeDecisionIn(BaseModel):
    unfreeze: bool = Field(description="true unfreezes the account; false keeps it frozen (refuses the appeal)")
    note: str = Field(min_length=5, max_length=2000, description="Reason, shown to the person")


@router.get("/freezes")
def freeze_cases(
    staff: Oversight,
    db: DB,
    status: Literal["open", "appealed", "closed", "all"] = "open",
    limit: Page = 100,
    offset: Offset = 0,
) -> list[FreezeCaseOut]:
    """Frozen accounts to review (appeals first), or decided ones."""
    return [FreezeCaseOut.model_validate(c) for c in freezes.cases(db, status, limit, offset)]


@router.post("/freezes/{case_id}/decide")
def decide_freeze(case_id: uuid.UUID, body: FreezeDecisionIn, staff: Oversight, db: DB) -> FreezeCaseOut:
    """Unfreeze, or keep frozen after an appeal. Must be someone other than the staff member who froze it."""
    case = freezes.decide(db, staff, case_id, body.unfreeze, body.note)
    db.commit()
    return FreezeCaseOut.model_validate(freezes.case_item(db, case))


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

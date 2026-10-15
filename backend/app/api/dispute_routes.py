"""Disputes API (ADR 0011): parties at /v1/disputes, staff at /v1/admin/disputes."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import audit
from app.auth.deps import current_user, require_role
from app.config import get_settings
from app.db import get_db
from app.disputes import service as disputes
from app.errors import AppError
from app.models import User

router = APIRouter(prefix="/v1")
DB = Annotated[Session, Depends(get_db)]
Me = Annotated[User, Depends(current_user)]
Staff = Annotated[User, Depends(require_role("support", "mediator", "compliance"))]
Mediator = Annotated[User, Depends(require_role("mediator"))]
Senior = Annotated[User, Depends(require_role("compliance"))]
Refund = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]

Stage = Literal["negotiation", "mediation", "decided", "appeal", "resolved"]
Who = Literal["buyer", "seller", "staff", "McXus"]


class PartyOut(BaseModel):
    id: uuid.UUID
    name: str


class DisputeSummaryOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    title: str
    amount: Decimal
    stage: Stage
    reason: str
    buyer: PartyOut
    seller: PartyOut
    opened_by: Literal["buyer", "seller"]
    opened_at: datetime
    deadline: datetime | None = Field(description="When the current stage ends (negotiation, mediator, appeal)")
    overdue: bool
    mediator: str | None
    mediator_id: uuid.UUID | None
    outcome: Literal["agreed", "mediator", "senior"] | None
    buyer_refund: Decimal | None


class DecisionOut(BaseModel):
    buyer_refund: Decimal
    note: str
    decided_at: datetime | None
    buyer_accepted: bool
    seller_accepted: bool


class AppealOut(BaseModel):
    by: Who
    reason: str
    at: datetime | None


class ResolutionOut(BaseModel):
    outcome: Literal["agreed", "mediator", "senior"] | None
    buyer_refund: Decimal | None
    seller_gets: Decimal
    note: str
    at: datetime | None


class OfferOut(BaseModel):
    id: uuid.UUID
    by: Who
    mine: bool
    buyer_refund: Decimal
    note: str
    status: Literal["open", "accepted", "rejected", "withdrawn", "replaced", "lapsed"]
    at: datetime


class EvidenceOut(BaseModel):
    id: uuid.UUID
    by: Who
    mine: bool
    kind: Literal["statement", "photo"]
    text: str
    width: int | None
    height: int | None
    at: datetime
    file: str | None = Field(description="Photo URL (needs the same sign-in)")


class TimelineOut(BaseModel):
    kind: str
    by: Who
    text: str
    at: datetime


class DisputeOut(DisputeSummaryOut):
    you: Literal["buyer", "seller", "staff"]
    actions: list[str] = Field(description="What you can do now, e.g. offer, escalate, appeal, decide")
    negotiate_until: datetime | None
    mediator_due: datetime | None
    appeal_until: datetime | None
    decision: DecisionOut | None
    appeal: AppealOut | None
    resolution: ResolutionOut | None
    offers: list[OfferOut]
    evidence: list[EvidenceOut]
    timeline: list[TimelineOut]


class OpenIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000, description="What went wrong (becomes your first statement)")


class OfferIn(BaseModel):
    buyer_refund: Refund = Field(description="How many Stars the buyer gets back; the seller gets the rest")
    note: str = Field(default="", max_length=500)


class AnswerIn(BaseModel):
    accept: bool = Field(description="true accepts (settles now); false rejects, or withdraws your own offer")


class StatementIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AppealIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class DecideIn(BaseModel):
    buyer_refund: Refund
    note: str = Field(min_length=5, max_length=2000, description="Reason, shown to both parties")


def _view(db: Session, user: User, order_id: uuid.UUID) -> DisputeOut:
    return DisputeOut.model_validate(disputes.view(db, user, order_id))


# ---------- parties ----------


@router.post("/orders/{order_id}/dispute", tags=["disputes"])
def open_dispute(order_id: uuid.UUID, body: OpenIn, user: Me, db: DB) -> DisputeOut:
    """Open a dispute: the order is frozen and 3 days of negotiation start."""
    disputes.open_dispute(db, user, order_id, body.reason)
    db.commit()
    return _view(db, user, order_id)


@router.get("/disputes", tags=["disputes"])
def my_disputes(user: Me, db: DB) -> list[DisputeSummaryOut]:
    return [DisputeSummaryOut.model_validate(d) for d in disputes.mine(db, user)]


@router.get("/disputes/{order_id}", tags=["disputes"])
def get_dispute(order_id: uuid.UUID, user: Me, db: DB) -> DisputeOut:
    return _view(db, user, order_id)


@router.post("/disputes/{order_id}/offers", status_code=201, tags=["disputes"])
def make_offer(order_id: uuid.UUID, body: OfferIn, user: Me, db: DB) -> DisputeOut:
    disputes.make_offer(db, user, order_id, body.buyer_refund, body.note)
    db.commit()
    return _view(db, user, order_id)


@router.post("/disputes/{order_id}/offers/{offer_id}", tags=["disputes"])
def answer_offer(order_id: uuid.UUID, offer_id: uuid.UUID, body: AnswerIn, user: Me, db: DB) -> DisputeOut:
    disputes.answer_offer(db, user, order_id, offer_id, body.accept)
    db.commit()
    return _view(db, user, order_id)


@router.post("/disputes/{order_id}/escalate", tags=["disputes"])
def escalate(order_id: uuid.UUID, user: Me, db: DB) -> DisputeOut:
    """Ask for a mediator now instead of waiting for the 3 days to end."""
    disputes.escalate(db, user, order_id)
    db.commit()
    return _view(db, user, order_id)


@router.post("/disputes/{order_id}/statements", status_code=201, tags=["disputes"])
def add_statement(order_id: uuid.UUID, body: StatementIn, user: Me, db: DB) -> DisputeOut:
    disputes.add_statement(db, user, order_id, body.text)
    db.commit()
    return _view(db, user, order_id)


@router.post("/disputes/{order_id}/photos", status_code=201, tags=["disputes"])
async def add_photo(order_id: uuid.UUID, file: UploadFile, user: Me, db: DB, caption: str = "") -> DisputeOut:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError(f"Photos must be under {get_settings().max_upload_mb} MB", code="photo_too_large")
    disputes.add_photo(db, user, order_id, data, caption)
    db.commit()
    return _view(db, user, order_id)


@router.get("/disputes/evidence/{evidence_id}", tags=["disputes"], response_class=Response)
def evidence_photo(evidence_id: uuid.UUID, user: Me, db: DB) -> Response:
    data = disputes.evidence_file(db, user, evidence_id)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.post("/disputes/{order_id}/accept-decision", tags=["disputes"])
def accept_decision(order_id: uuid.UUID, user: Me, db: DB) -> DisputeOut:
    """Accept the mediator's decision. When both accept, it is final at once."""
    disputes.accept_decision(db, user, order_id)
    db.commit()
    return _view(db, user, order_id)


@router.post("/disputes/{order_id}/appeal", tags=["disputes"])
def appeal(order_id: uuid.UUID, body: AppealIn, user: Me, db: DB) -> DisputeOut:
    """Appeal the mediator's decision (once, within 3 days). A senior staff member decides; that is final."""
    disputes.appeal(db, user, order_id, body.reason)
    db.commit()
    return _view(db, user, order_id)


# ---------- staff ----------


@router.get("/admin/disputes", tags=["staff"])
def dispute_queue(
    staff: Staff,
    db: DB,
    stage: Stage | None = None,
    mine: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DisputeSummaryOut]:
    """Active disputes, overdue first then by deadline; or one stage (e.g. resolved)."""
    return [DisputeSummaryOut.model_validate(d) for d in disputes.queue(db, staff, stage, mine, limit, offset)]


@router.get("/admin/disputes/counts", tags=["staff"])
def dispute_counts(staff: Staff, db: DB) -> dict[str, int]:
    return disputes.counts(db)


@router.get("/admin/disputes/{order_id}", tags=["staff"])
def staff_view(order_id: uuid.UUID, staff: Staff, db: DB) -> DisputeOut:
    return _view(db, staff, order_id)


@router.post("/admin/disputes/{order_id}/take", tags=["staff"])
def take_case(order_id: uuid.UUID, staff: Mediator, db: DB) -> DisputeOut:
    disputes.take_case(db, staff, order_id)
    audit.record(db, staff, "dispute_taken", "order", order_id)
    db.commit()
    return _view(db, staff, order_id)


@router.post("/admin/disputes/{order_id}/decide", tags=["staff"])
def decide(order_id: uuid.UUID, body: DecideIn, staff: Mediator, db: DB) -> DisputeOut:
    """Mediator's decision. Money moves when the 3-day appeal window ends or both parties accept."""
    disputes.decide(db, staff, order_id, body.buyer_refund, body.note)
    audit.record(db, staff, "dispute_decided", "order", order_id, f"Buyer gets back K{body.buyer_refund}. {body.note}")
    db.commit()
    return _view(db, staff, order_id)


@router.post("/admin/disputes/{order_id}/final", tags=["staff"])
def final_decision(order_id: uuid.UUID, body: DecideIn, staff: Senior, db: DB) -> DisputeOut:
    """Senior (compliance/admin) decision on an appeal. Final; money moves now."""
    disputes.final_decision(db, staff, order_id, body.buyer_refund, body.note)
    audit.record(db, staff, "appeal_decided", "order", order_id, f"Buyer gets back K{body.buyer_refund}. {body.note}")
    db.commit()
    return _view(db, staff, order_id)

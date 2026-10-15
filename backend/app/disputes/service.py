"""Three-stage disputes (ADR 0011).

    order DISPUTED, Stars frozen in escrow
      1. negotiation (3 days): buyer and seller make offers ("buyer gets back K__"); accepting one settles it.
         Either can ask for a mediator at once; when the 3 days pass it goes to a mediator automatically.
      2. mediation (5 PNG working days): a mediator reads both sides' statements and photos and decides a refund.
         The parties can still settle with an offer until the mediator decides.
      3. decided (3 days to appeal): the decision becomes final when the window ends or both parties accept it.
         Either party may appeal once -> appeal: a senior staff member (compliance or admin, not the mediator)
         makes the final decision.
    resolved: money moved in one ledger entry (refund to buyer, rest to seller less the 3% escrow fee).

Who sees what: both parties and staff see the whole case (offers, statements, photos, decisions). Evidence is
not end-to-end encrypted, because the mediator must read it; photos lose their metadata (GPS) on upload.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.disputes.calendar import add_working_days
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.escrow import service as escrow
from app.marketplace import media
from app.models import Dispute, DisputeEvent, DisputeEvidence, DisputeOffer, Order, User
from app.money import ZERO

STAFF_VIEW = ("support", "mediator", "compliance", "admin")
MEDIATORS = ("mediator", "admin")
SENIOR = ("compliance", "admin")
ACTIVE = ("negotiation", "mediation", "decided", "appeal")


# ---------- loading and access ----------


def _load(db: Session, order_id: uuid.UUID, *, lock: bool = False) -> tuple[Dispute, Order]:
    stmt = select(Dispute).where(Dispute.order_id == order_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    dispute = db.scalars(stmt).first()
    if dispute is None:
        raise NotFound("No dispute on this order")
    order = escrow.get_order(db, order_id)
    return dispute, order


def _party(order: Order, user: User) -> str | None:
    if user.id == order.buyer_id:
        return "buyer"
    if user.id == order.seller_id:
        return "seller"
    return None


def _require_party(order: Order, user: User) -> str:
    party = _party(order, user)
    if party is None:
        raise Forbidden("Only the buyer or the seller can do this")
    return party


def _require_staff(order: Order, user: User, roles: tuple[str, ...]) -> None:
    if user.role not in roles:
        raise Forbidden("Your role cannot do this")
    if _party(order, user) is not None:
        raise Forbidden("You cannot decide a dispute you are part of")


def _stage(dispute: Dispute, *stages: str) -> None:
    if dispute.status not in stages:
        raise Conflict(f"This dispute is at the {dispute.status} stage", code="wrong_stage")


def _event(db: Session, dispute: Dispute, actor: User | None, kind: str, text: str = "") -> None:
    db.add(
        DisputeEvent(
            dispute_id=dispute.id, actor_id=actor.id if actor else None, kind=kind, text=text, created_at=clock.now()
        )
    )


def _check_refund(order: Order, amount: Decimal) -> None:
    if not ZERO <= amount <= order.amount:
        raise AppError(f"The refund must be between K0 and K{order.amount}", code="invalid_refund")


def _text(value: str, field: str, limit: int = 2000) -> str:
    value = value.strip()
    if not value:
        raise AppError(f"Write a {field}", code=f"{field.replace(' ', '_')}_required")
    if len(value) > limit:
        raise AppError(f"Keep the {field} under {limit} characters", code="too_long")
    return value


def _lapse_offers(db: Session, dispute: Dispute) -> None:
    for offer in db.scalars(
        select(DisputeOffer).where(DisputeOffer.dispute_id == dispute.id, DisputeOffer.status == "open")
    ):
        offer.status = "lapsed"
        offer.answered_at = clock.now()


def _settle(db: Session, dispute: Dispute, refund: Decimal, actor: User | None, note: str, outcome: str) -> None:
    _lapse_offers(db, dispute)
    escrow.settle_dispute(db, dispute.order_id, refund, actor.id if actor else None, note, outcome)
    how = {
        "agreed": "By agreement",
        "mediator": "The mediator's decision is final",
        "senior": "Final decision on the appeal",
    }
    _event(db, dispute, actor, "resolved", f"{how[outcome]}: buyer gets back K{refund}")


# ---------- stage 1: open and negotiate ----------


def open_dispute(db: Session, user: User, order_id: uuid.UUID, reason: str) -> Dispute:
    dispute = escrow.open_dispute(db, user, order_id, reason)
    _event(db, dispute, user, "opened", dispute.reason)
    db.add(
        DisputeEvidence(
            dispute_id=dispute.id, user_id=user.id, kind="statement", text=dispute.reason, created_at=clock.now()
        )
    )
    return dispute


def make_offer(db: Session, user: User, order_id: uuid.UUID, buyer_refund: Decimal, note: str = "") -> DisputeOffer:
    dispute, order = _load(db, order_id, lock=True)
    _require_party(order, user)
    _stage(dispute, "negotiation", "mediation")
    _check_refund(order, buyer_refund)
    for old in db.scalars(
        select(DisputeOffer).where(
            DisputeOffer.dispute_id == dispute.id, DisputeOffer.by_user_id == user.id, DisputeOffer.status == "open"
        )
    ):
        old.status = "replaced"
        old.answered_at = clock.now()
    offer = DisputeOffer(
        id=uuid.uuid4(),
        dispute_id=dispute.id,
        by_user_id=user.id,
        buyer_refund=buyer_refund,
        note=note.strip()[:500],
        created_at=clock.now(),
    )
    db.add(offer)
    _event(db, dispute, user, "offer", f"Offer: buyer gets back K{buyer_refund}")
    db.flush()
    return offer


def answer_offer(db: Session, user: User, order_id: uuid.UUID, offer_id: uuid.UUID, accept: bool) -> Dispute:
    """The other party accepts (settles the dispute at once) or rejects an offer; the maker may withdraw it."""
    dispute, order = _load(db, order_id, lock=True)
    _require_party(order, user)
    _stage(dispute, "negotiation", "mediation")
    offer = db.get(DisputeOffer, offer_id, with_for_update=True)
    if offer is None or offer.dispute_id != dispute.id:
        raise NotFound("Offer not found")
    if offer.status != "open":
        raise Conflict(f"This offer was {offer.status}", code="offer_closed")
    offer.answered_at = clock.now()
    if offer.by_user_id == user.id:
        if accept:
            raise Conflict("You cannot accept your own offer", code="own_offer")
        offer.status = "withdrawn"
        _event(db, dispute, user, "offer_withdrawn")
        return dispute
    if not accept:
        offer.status = "rejected"
        _event(db, dispute, user, "offer_rejected", f"Rejected: buyer gets back K{offer.buyer_refund}")
        return dispute
    offer.status = "accepted"
    _event(db, dispute, user, "offer_accepted", f"Agreed: buyer gets back K{offer.buyer_refund}")
    _settle(db, dispute, offer.buyer_refund, user, offer.note or "Buyer and seller agreed", "agreed")
    return dispute


def _to_mediation(db: Session, dispute: Dispute, actor: User | None, why: str) -> None:
    now = clock.now()
    dispute.status = "mediation"
    dispute.escalated_at = now
    dispute.mediator_due = add_working_days(now, get_settings().dispute_mediator_business_days)
    _event(db, dispute, actor, "escalated", why)


def escalate(db: Session, user: User, order_id: uuid.UUID) -> Dispute:
    dispute, order = _load(db, order_id, lock=True)
    party = _require_party(order, user)
    _stage(dispute, "negotiation")
    _to_mediation(db, dispute, user, f"The {party} asked for a mediator")
    return dispute


# ---------- evidence ----------


def _count(db: Session, dispute: Dispute, user: User, kind: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(DisputeEvidence)
            .where(
                DisputeEvidence.dispute_id == dispute.id,
                DisputeEvidence.user_id == user.id,
                DisputeEvidence.kind == kind,
            )
        )
        or 0
    )


def add_statement(db: Session, user: User, order_id: uuid.UUID, text: str) -> DisputeEvidence:
    dispute, order = _load(db, order_id, lock=True)
    _require_party(order, user)
    _stage(dispute, *ACTIVE)
    limit = get_settings().dispute_max_statements
    if _count(db, dispute, user, "statement") >= limit:
        raise Conflict(f"You can add up to {limit} statements", code="too_many_statements")
    item = DisputeEvidence(
        id=uuid.uuid4(),
        dispute_id=dispute.id,
        user_id=user.id,
        kind="statement",
        text=_text(text, "statement"),
        created_at=clock.now(),
    )
    db.add(item)
    _event(db, dispute, user, "statement")
    db.flush()
    return item


def _evidence_storage() -> media.LocalStorage:
    return media.LocalStorage(get_settings().evidence_dir)


def add_photo(db: Session, user: User, order_id: uuid.UUID, data: bytes, caption: str = "") -> DisputeEvidence:
    dispute, order = _load(db, order_id, lock=True)
    _require_party(order, user)
    _stage(dispute, *ACTIVE)
    limit = get_settings().dispute_max_photos
    if _count(db, dispute, user, "photo") >= limit:
        raise Conflict(f"You can add up to {limit} photos", code="too_many_photos")
    photo = media.process(data)  # validates, strips GPS and other metadata, resizes
    item_id = uuid.uuid4()
    key = f"{dispute.id}/{item_id}.jpg"
    _evidence_storage().save(key, photo.full)
    item = DisputeEvidence(
        id=item_id,
        dispute_id=dispute.id,
        user_id=user.id,
        kind="photo",
        text=caption.strip()[:300],
        file_key=key,
        width=photo.width,
        height=photo.height,
        created_at=clock.now(),
    )
    db.add(item)
    _event(db, dispute, user, "photo")
    db.flush()
    return item


def evidence_file(db: Session, user: User, evidence_id: uuid.UUID) -> bytes:
    item = db.get(DisputeEvidence, evidence_id)
    if item is None or item.file_key is None:
        raise NotFound("Photo not found")
    dispute = db.get(Dispute, item.dispute_id)
    assert dispute is not None
    order = escrow.get_order(db, dispute.order_id)
    if _party(order, user) is None and user.role not in STAFF_VIEW:
        raise NotFound("Photo not found")
    path = Path(get_settings().evidence_dir) / item.file_key
    if not path.is_file():
        raise NotFound("Photo not found")
    return path.read_bytes()


# ---------- stage 2: mediator ----------


def take_case(db: Session, staff: User, order_id: uuid.UUID) -> Dispute:
    dispute, order = _load(db, order_id, lock=True)
    _require_staff(order, staff, MEDIATORS)
    _stage(dispute, "negotiation", "mediation")
    if dispute.status == "negotiation":
        _to_mediation(db, dispute, staff, "A mediator took the case")
    dispute.mediator_id = staff.id
    _event(db, dispute, staff, "assigned", f"Mediator: {staff.display_name or 'staff'}")
    return dispute


def decide(db: Session, staff: User, order_id: uuid.UUID, buyer_refund: Decimal, note: str) -> Dispute:
    dispute, order = _load(db, order_id, lock=True)
    _require_staff(order, staff, MEDIATORS)
    _stage(dispute, "mediation")
    _check_refund(order, buyer_refund)
    now = clock.now()
    _lapse_offers(db, dispute)
    dispute.status = "decided"
    dispute.mediator_id = dispute.mediator_id or staff.id
    dispute.proposed_refund = buyer_refund
    dispute.proposed_note = _text(note, "reason for the decision")
    dispute.decided_by = staff.id
    dispute.decided_at = now
    dispute.appeal_until = now + timedelta(days=get_settings().dispute_appeal_days)
    _event(db, dispute, staff, "decided", f"buyer gets back K{buyer_refund}. {dispute.proposed_note}")
    return dispute


# ---------- stage 3: accept or appeal ----------


def accept_decision(db: Session, user: User, order_id: uuid.UUID) -> Dispute:
    dispute, order = _load(db, order_id, lock=True)
    party = _require_party(order, user)
    _stage(dispute, "decided")
    if party == "buyer":
        dispute.buyer_accepted = True
    else:
        dispute.seller_accepted = True
    _event(db, dispute, user, "accepted", f"The {party} accepted the decision")
    if dispute.buyer_accepted and dispute.seller_accepted:
        assert dispute.proposed_refund is not None
        _settle(db, dispute, dispute.proposed_refund, None, dispute.proposed_note, "mediator")
    return dispute


def appeal(db: Session, user: User, order_id: uuid.UUID, reason: str) -> Dispute:
    dispute, order = _load(db, order_id, lock=True)
    party = _require_party(order, user)
    _stage(dispute, "decided")
    if dispute.appeal_until is not None and clock.now() >= dispute.appeal_until:
        raise Conflict("The time to appeal has ended", code="appeal_closed")
    accepted = dispute.buyer_accepted if party == "buyer" else dispute.seller_accepted
    if accepted:
        raise Conflict("You already accepted the decision", code="already_accepted")
    dispute.status = "appeal"
    dispute.appealed_by = user.id
    dispute.appeal_reason = _text(reason, "reason for the appeal")
    dispute.appealed_at = clock.now()
    _event(db, dispute, user, "appealed", dispute.appeal_reason)
    return dispute


def final_decision(db: Session, staff: User, order_id: uuid.UUID, buyer_refund: Decimal, note: str) -> Dispute:
    dispute, order = _load(db, order_id, lock=True)
    _require_staff(order, staff, SENIOR)
    _stage(dispute, "appeal")
    if staff.id == dispute.decided_by:
        raise Forbidden("The appeal must be decided by someone other than the mediator")
    _check_refund(order, buyer_refund)
    _settle(db, dispute, buyer_refund, staff, _text(note, "reason for the decision"), "senior")
    return dispute


# ---------- deadlines (run by the worker) ----------


def due_dispute_ids(db: Session, now: datetime, limit: int = 500) -> list[uuid.UUID]:
    rows = db.scalars(
        select(Dispute.order_id)
        .where(
            ((Dispute.status == "negotiation") & (Dispute.negotiate_until <= now))
            | ((Dispute.status == "decided") & (Dispute.appeal_until <= now))
        )
        .limit(limit)
    )
    return list(rows)


def apply_deadline(db: Session, order_id: uuid.UUID) -> str | None:
    dispute, _order = _load(db, order_id, lock=True)
    now = clock.now()
    if dispute.status == "negotiation" and dispute.negotiate_until and dispute.negotiate_until <= now:
        _to_mediation(db, dispute, None, f"No agreement within {get_settings().dispute_negotiate_days} days")
        return "dispute_mediation"
    if dispute.status == "decided" and dispute.appeal_until and dispute.appeal_until <= now:
        assert dispute.proposed_refund is not None
        _settle(db, dispute, dispute.proposed_refund, None, dispute.proposed_note, "mediator")
        return "dispute_resolved"
    return None


# ---------- views ----------


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    real = {i for i in ids if i is not None}
    if not real:
        return {}
    return {u.id: u.display_name or "McXus user" for u in db.scalars(select(User).where(User.id.in_(real)))}


def _deadline(dispute: Dispute) -> datetime | None:
    return {
        "negotiation": dispute.negotiate_until,
        "mediation": dispute.mediator_due,
        "decided": dispute.appeal_until,
    }.get(dispute.status)


def summary(dispute: Dispute, order: Order, names: dict[uuid.UUID, str], now: datetime) -> dict[str, Any]:
    deadline = _deadline(dispute)
    return {
        "id": dispute.id,
        "order_id": order.id,
        "title": order.title,
        "amount": order.amount,
        "stage": dispute.status,
        "reason": dispute.reason,
        "buyer": {"id": order.buyer_id, "name": names.get(order.buyer_id, "Buyer")},
        "seller": {"id": order.seller_id, "name": names.get(order.seller_id, "Seller")},
        "opened_by": "buyer" if dispute.opened_by == order.buyer_id else "seller",
        "opened_at": dispute.created_at,
        "deadline": deadline,
        # Only a late mediator needs staff attention; other deadlines are applied by the worker.
        "overdue": dispute.status == "mediation" and deadline is not None and deadline <= now,
        "mediator": names.get(dispute.mediator_id) if dispute.mediator_id else None,
        "mediator_id": dispute.mediator_id,
        "outcome": dispute.outcome,
        "buyer_refund": dispute.buyer_refund,
    }


def view(db: Session, user: User, order_id: uuid.UUID) -> dict[str, Any]:
    """Everything about one dispute, plus which actions this user may take now (the apps show only those)."""
    dispute, order = _load(db, order_id)
    party = _party(order, user)
    if party is None and user.role not in STAFF_VIEW:
        raise NotFound("No dispute on this order")
    offers = list(
        db.scalars(select(DisputeOffer).where(DisputeOffer.dispute_id == dispute.id).order_by(DisputeOffer.created_at))
    )
    evidence = list(
        db.scalars(
            select(DisputeEvidence).where(DisputeEvidence.dispute_id == dispute.id).order_by(DisputeEvidence.created_at)
        )
    )
    events = list(
        db.scalars(select(DisputeEvent).where(DisputeEvent.dispute_id == dispute.id).order_by(DisputeEvent.id))
    )
    names = _names(
        db,
        {
            order.buyer_id,
            order.seller_id,
            dispute.mediator_id,
            dispute.decided_by,
            dispute.resolved_by,
            *(e.actor_id for e in events),
        },
    )
    now = clock.now()

    def who(user_id: uuid.UUID | None) -> str:
        if user_id is None:
            return "McXus"
        if user_id == order.buyer_id:
            return "buyer"
        if user_id == order.seller_id:
            return "seller"
        return "staff"

    s = dispute.status
    accepted = {"buyer": dispute.buyer_accepted, "seller": dispute.seller_accepted}
    actions: list[str] = []
    if party:
        if s in ("negotiation", "mediation"):
            actions += ["offer"]
        if s == "negotiation":
            actions += ["escalate"]
        if s in ACTIVE:
            actions += ["statement", "photo"]
        if s == "decided" and not accepted[party]:
            actions += ["accept_decision"]
            if dispute.appeal_until is None or now < dispute.appeal_until:
                actions += ["appeal"]
    elif party is None:
        if user.role in MEDIATORS and s in ("negotiation", "mediation"):
            actions += ["take_case"]
        if user.role in MEDIATORS and s == "mediation":
            actions += ["decide"]
        if user.role in SENIOR and s == "appeal" and user.id != dispute.decided_by:
            actions += ["final_decision"]

    return {
        **summary(dispute, order, names, now),
        "you": party or "staff",
        "actions": actions,
        "negotiate_until": dispute.negotiate_until,
        "mediator_due": dispute.mediator_due,
        "appeal_until": dispute.appeal_until,
        "decision": None
        if dispute.proposed_refund is None
        else {
            "buyer_refund": dispute.proposed_refund,
            "note": dispute.proposed_note,
            "decided_at": dispute.decided_at,
            "buyer_accepted": dispute.buyer_accepted,
            "seller_accepted": dispute.seller_accepted,
        },
        "appeal": None
        if dispute.appealed_by is None
        else {
            "by": who(dispute.appealed_by),
            "reason": dispute.appeal_reason,
            "at": dispute.appealed_at,
        },
        "resolution": None
        if dispute.status != "resolved"
        else {
            "outcome": dispute.outcome,
            "buyer_refund": dispute.buyer_refund,
            "seller_gets": order.amount - (dispute.buyer_refund or ZERO),
            "note": dispute.decision_note,
            "at": dispute.resolved_at,
        },
        "offers": [
            {
                "id": o.id,
                "by": who(o.by_user_id),
                "mine": o.by_user_id == user.id,
                "buyer_refund": o.buyer_refund,
                "note": o.note,
                "status": o.status,
                "at": o.created_at,
            }
            for o in offers
        ],
        "evidence": [
            {
                "id": e.id,
                "by": who(e.user_id),
                "mine": e.user_id == user.id,
                "kind": e.kind,
                "text": e.text,
                "width": e.width,
                "height": e.height,
                "at": e.created_at,
                "file": f"/v1/disputes/evidence/{e.id}" if e.file_key else None,
            }
            for e in evidence
        ],
        "timeline": [{"kind": e.kind, "by": who(e.actor_id), "text": e.text, "at": e.created_at} for e in events],
    }


def mine(db: Session, user: User) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Dispute, Order)
        .join(Order, Order.id == Dispute.order_id)
        .where((Order.buyer_id == user.id) | (Order.seller_id == user.id))
        .order_by(Dispute.created_at.desc())
        .limit(100)
    ).all()
    ids: set[uuid.UUID | None] = set()
    for _, o in rows:
        ids |= {o.buyer_id, o.seller_id}
    names = _names(db, ids)
    now = clock.now()
    return [summary(d, o, names, now) for d, o in rows]


def queue(
    db: Session, staff: User, stage: str | None, assigned_to_me: bool, limit: int, offset: int
) -> list[dict[str, Any]]:
    """Staff queue: active disputes first by deadline (overdue on top), or one stage."""
    stmt = select(Dispute, Order).join(Order, Order.id == Dispute.order_id)
    stmt = stmt.where(Dispute.status == stage) if stage else stmt.where(Dispute.status.in_(ACTIVE))
    if assigned_to_me:
        stmt = stmt.where(Dispute.mediator_id == staff.id)
    rows = db.execute(stmt.order_by(Dispute.created_at).limit(limit).offset(offset)).all()
    ids: set[uuid.UUID | None] = set()
    for d, o in rows:
        ids |= {o.buyer_id, o.seller_id, d.mediator_id}
    names = _names(db, ids)
    now = clock.now()
    items = [summary(d, o, names, now) for d, o in rows]
    far = datetime.max.replace(tzinfo=now.tzinfo)
    return sorted(items, key=lambda i: (not i["overdue"], i["deadline"] or far))


def counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(Dispute.status, func.count()).group_by(Dispute.status)).all()
    return {status: n for status, n in rows}

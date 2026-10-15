"""Freezing and unfreezing accounts (M4.1).

    staff freezes (reason) ──> frozen ──person appeals once──> appealed
                                  │                               │
              a different staff member decides: unfreeze (note) or keep frozen (note: "upheld")

- A frozen person can still sign in, see why the account is frozen and send one appeal; nothing else works.
- Unfreezing, or refusing an appeal, must be done by someone other than the staff member who froze the account
  (two people for every freeze). Admin is not exempt.
- Every step is in the staff activity log.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, clock
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.models import AccountFreeze, User

OPEN = ("frozen", "appealed")


def _text(value: str, what: str, minimum: int = 5) -> str:
    value = value.strip()
    if len(value) < minimum:
        raise AppError(f"Write the {what} (at least {minimum} characters)", code="text_required")
    return value[:2000]


def open_case(db: Session, user_id: uuid.UUID) -> AccountFreeze | None:
    return db.scalars(
        select(AccountFreeze)
        .where(AccountFreeze.user_id == user_id, AccountFreeze.status.in_(OPEN))
        .order_by(AccountFreeze.frozen_at.desc())
        .with_for_update()
    ).first()


def latest_case(db: Session, user_id: uuid.UUID) -> AccountFreeze | None:
    return db.scalars(
        select(AccountFreeze).where(AccountFreeze.user_id == user_id).order_by(AccountFreeze.frozen_at.desc())
    ).first()


def freeze(db: Session, staff: User, user: User, reason: str) -> AccountFreeze:
    if user.id == staff.id:
        raise AppError("You cannot freeze your own account", code="own_account")
    if user.status == "frozen":
        raise Conflict("This account is already frozen", code="already_frozen")
    case = AccountFreeze(
        id=uuid.uuid4(),
        user_id=user.id,
        status="frozen",
        reason=_text(reason, "reason"),
        frozen_by=staff.id,
        frozen_at=clock.now(),
        created_at=clock.now(),
    )
    db.add(case)
    user.status = "frozen"
    audit.record(db, staff, "user_frozen", "user", user.id, case.reason)
    return case


def _decide(db: Session, staff: User, case: AccountFreeze, user: User, unfreeze: bool, note: str) -> AccountFreeze:
    if case.frozen_by == staff.id:
        raise Forbidden("Someone other than the person who froze this account must decide", code="same_person")
    if user.id == staff.id:
        raise Forbidden("You cannot decide about your own account", code="own_account")
    if not unfreeze and case.status != "appealed":
        raise Conflict("Only an appeal can be refused; the account is already frozen", code="no_appeal")
    case.decision_note = _text(note, "reason for the decision")
    case.decided_by = staff.id
    case.decided_at = clock.now()
    case.status = "unfrozen" if unfreeze else "upheld"
    if unfreeze:
        user.status = "active"
    audit.record(db, staff, "user_active" if unfreeze else "freeze_upheld", "user", user.id, case.decision_note)
    return case


def unfreeze(db: Session, staff: User, user: User, note: str) -> AccountFreeze:
    case = open_case(db, user.id)
    if user.status != "frozen" or case is None:
        raise Conflict("This account is not frozen", code="not_frozen")
    return _decide(db, staff, case, user, True, note)


def decide(db: Session, staff: User, case_id: uuid.UUID, unfreeze_it: bool, note: str) -> AccountFreeze:
    case = db.get(AccountFreeze, case_id, with_for_update=True)
    if case is None:
        raise NotFound("Freeze not found")
    if case.status not in OPEN:
        raise Conflict(f"This freeze was already decided ({case.status})", code="already_decided")
    user = db.get(User, case.user_id)
    assert user is not None
    return _decide(db, staff, case, user, unfreeze_it, note)


def appeal(db: Session, user: User, text: str) -> AccountFreeze:
    case = open_case(db, user.id)
    if user.status != "frozen" or case is None:
        raise Conflict("Your account is not frozen", code="not_frozen")
    if case.status != "frozen":
        raise Conflict("You already appealed. Staff will reply here.", code="already_appealed")
    case.appeal_text = _text(text, "appeal", 10)
    case.appealed_at = clock.now()
    case.status = "appealed"
    return case


def view(case: AccountFreeze | None, names: dict[uuid.UUID, str] | None = None) -> dict[str, Any] | None:
    if case is None:
        return None
    names = names or {}
    return {
        "id": case.id,
        "user_id": case.user_id,
        "status": case.status,
        "reason": case.reason,
        "frozen_at": case.frozen_at,
        "frozen_by": names.get(case.frozen_by) if case.frozen_by else None,
        "frozen_by_id": case.frozen_by,
        "appeal_text": case.appeal_text,
        "appealed_at": case.appealed_at,
        "decision_note": case.decision_note,
        "decided_at": case.decided_at,
        "decided_by": names.get(case.decided_by) if case.decided_by else None,
        "can_appeal": case.status == "frozen",
    }


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    real = {i for i in ids if i}
    if not real:
        return {}
    return {u.id: u.display_name or u.phone or "staff" for u in db.scalars(select(User).where(User.id.in_(real)))}


def _item(case: AccountFreeze, user: User, names: dict[uuid.UUID, str]) -> dict[str, Any]:
    item = view(case, names) or {}
    item["user"] = {"id": user.id, "name": user.display_name or "No name", "phone": user.phone, "status": user.status}
    return item


def case_item(db: Session, case: AccountFreeze) -> dict[str, Any]:
    user = db.get(User, case.user_id)
    assert user is not None
    return _item(case, user, _names(db, {case.frozen_by, case.decided_by}))


def cases(db: Session, status: str, limit: int, offset: int) -> list[dict[str, Any]]:
    """Open freezes (appeals first, then oldest), or closed ones, or all."""
    stmt = select(AccountFreeze, User).join(User, User.id == AccountFreeze.user_id)
    if status == "open":
        stmt = stmt.where(AccountFreeze.status.in_(OPEN))
    elif status == "appealed":
        stmt = stmt.where(AccountFreeze.status == "appealed")
    elif status == "closed":
        stmt = stmt.where(AccountFreeze.status.in_(("unfrozen", "upheld")))
    rows = db.execute(stmt.order_by(AccountFreeze.frozen_at.desc()).limit(limit).offset(offset)).all()
    ids: set[uuid.UUID | None] = set()
    for case, _ in rows:
        ids |= {case.frozen_by, case.decided_by}
    names = _names(db, ids)
    out = [_item(case, user, names) for case, user in rows]
    if status == "open":
        out.sort(key=lambda i: (i["status"] != "appealed", i["frozen_at"]))
    return out

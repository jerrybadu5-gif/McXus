"""Staff audit trail: who did what to which user, order, deposit, listing or dispute."""

from sqlalchemy.orm import Session

from app import clock
from app.models import StaffAction, User


def record(db: Session, actor: User, action: str, target_type: str, target_id: object, detail: str = "") -> None:
    db.add(
        StaffAction(
            actor_id=actor.id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            detail=detail[:2000],
            created_at=clock.now(),
        )
    )

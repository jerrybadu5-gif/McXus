"""Idempotency for money actions.

The app sends an `Idempotency-Key` header (a fresh UUID per tap). If the network drops and the phone retries
with the same key, the stored result is returned and the money moves only once.
"""

import hashlib
import json
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError, Conflict
from app.models import IdempotencyKey


def run_once(
    db: Session, user_id: uuid.UUID, key: str | None, request: dict[str, Any], action: Callable[[], Any]
) -> Any:
    """Run `action` and commit, unless this key was already used (then return the stored result)."""
    if not key or len(key) > 80:
        raise AppError(
            "Send an Idempotency-Key header (max 80 characters) with money actions", code="idempotency_key_required"
        )
    request_hash = hashlib.sha256(json.dumps(_encode(request), sort_keys=True).encode()).hexdigest()
    stored = db.get(IdempotencyKey, (user_id, key))
    if stored is not None:
        if stored.request_hash != request_hash:
            raise AppError(
                "This Idempotency-Key was already used for a different request", code="idempotency_key_reused"
            )
        return stored.response_body

    body = _encode(action())
    db.add(IdempotencyKey(user_id=user_id, key=key, request_hash=request_hash, response_status=200, response_body=body))
    try:
        db.commit()
    except IntegrityError as exc:  # the same key arrived twice at the same moment; the other one won
        db.rollback()
        raise Conflict("This request is already being processed", code="idempotency_in_progress") from exc
    return body


def _encode(value: Any) -> Any:
    """JSON-safe copy that keeps money exact (Decimal -> "12.50", never a float)."""
    return jsonable_encoder(value, custom_encoder={Decimal: str})

"""Finding people by name or phone: not case-sensitive, words in any order, made for search-as-you-type."""

import re
import uuid
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models import User


def _like(text: str) -> str:
    return "%" + re.sub(r"([%_\\])", r"\\\1", text) + "%"


def match(q: str, *, min_phone_digits: int = 3) -> ColumnElement[bool] | None:
    """A WHERE clause for `q`, or None if there is nothing to search for.

    - A full account id matches that account.
    - Every word must appear in the name or store name (any case, any order): "seller demo" finds "Demo Seller".
    - Digits match the phone number (staff: 3 or more digits; customers: almost the whole number).
    """
    q = q.strip()
    if not q:
        return None
    try:
        return User.id == uuid.UUID(q)
    except ValueError:
        pass
    words = [w for w in re.split(r"\s+", q) if w and not w.isdigit() and not w.startswith("+")]
    digits = "".join(ch for ch in q if ch.isdigit())
    conditions: list[ColumnElement[bool]] = []
    if words:
        name = func.concat(func.coalesce(User.display_name, ""), " ", func.coalesce(User.store_name, ""))
        conditions.append(and_(*[name.ilike(_like(w), escape="\\") for w in words]))
    if len(digits) >= min_phone_digits:
        conditions.append(User.phone.like(_like(digits[-8:])))
    return or_(*conditions) if conditions else None


def card(user: User) -> dict[str, Any]:
    """What one customer may see about another in search results: name and the last 3 digits of the phone."""
    phone = user.phone or ""
    return {
        "id": user.id,
        "name": user.store_name or user.display_name or "McXus user",
        "phone_hint": f"…{phone[-3:]}" if phone else "",
    }

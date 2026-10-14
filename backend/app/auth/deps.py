"""FastAPI dependencies: current user and role checks (always enforced server-side)."""

from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.service import decode_token
from app.db import get_db
from app.errors import Forbidden, Unauthorized
from app.models import User

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise Unauthorized("Sign in first")
    user = db.get(User, decode_token(creds.credentials))
    if user is None:
        raise Unauthorized("Sign in again")
    if user.status != "active":
        raise Forbidden("This account is frozen. Contact support.", code="account_frozen")
    return user


def require_role(*roles: str) -> Callable[..., User]:
    """Staff endpoints. 'admin' can do everything."""

    def check(user: User = Depends(current_user)) -> User:
        if user.role != "admin" and user.role not in roles:
            raise Forbidden("Your role cannot do this")
        return user

    return check

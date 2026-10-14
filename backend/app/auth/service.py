"""Phone sign-in with one-time codes, and JWT access tokens.

SMS sending is a stub for now: in dev/test the code is written to the server log (console provider).
"""

import hashlib
import hmac
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.errors import AppError, TooManyRequests, Unauthorized
from app.ledger.service import ensure_user_accounts
from app.models import OtpCode, User

log = logging.getLogger("mcxus.sms")
PHONE_RE = re.compile(r"^\+675[0-9]{7,8}$")


def normalise_phone(raw: str) -> str:
    """Accept '7xxxxxxx', '07xxxxxxx', '675...' or '+675...' and return '+675xxxxxxxx'."""
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("+"):
        phone = digits
    elif digits.startswith("675"):
        phone = "+" + digits
    else:
        phone = "+675" + digits.lstrip("0")
    if not PHONE_RE.match(phone):
        raise AppError("Enter a PNG mobile number, e.g. 7xxxxxxx", code="invalid_phone")
    return phone


def _hash_code(phone: str, code: str) -> str:
    key = get_settings().otp_secret.encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def request_code(db: Session, raw_phone: str) -> None:
    settings = get_settings()
    phone = normalise_phone(raw_phone)
    now = clock.now()
    recent = db.scalar(
        select(func.count())
        .select_from(OtpCode)
        .where(OtpCode.phone == phone, OtpCode.created_at > now - timedelta(minutes=10))
    )
    if recent is not None and recent >= settings.otp_max_per_10_min:
        raise TooManyRequests("Too many codes requested. Try again in 10 minutes.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        OtpCode(
            phone=phone,
            code_hash=_hash_code(phone, code),
            created_at=now,
            expires_at=now + timedelta(minutes=settings.otp_ttl_minutes),
        )
    )
    send_sms(phone, f"Your McXus code is {code}. It expires in {settings.otp_ttl_minutes} minutes.")


def send_sms(phone: str, text: str) -> None:
    """Console SMS provider. Replace with a real provider adapter before launch."""
    log.warning("SMS to %s: %s", phone, text)


def verify_code(db: Session, raw_phone: str, code: str) -> User:
    settings = get_settings()
    phone = normalise_phone(raw_phone)
    now = clock.now()
    otp = db.scalars(
        select(OtpCode)
        .where(OtpCode.phone == phone, OtpCode.used_at.is_(None), OtpCode.expires_at > now)
        .order_by(OtpCode.created_at.desc())
        .limit(1)
        .with_for_update()
    ).first()
    if otp is None or otp.attempts >= settings.otp_max_attempts:
        raise Unauthorized("Code expired or too many attempts. Request a new code.", code="otp_invalid")
    if not hmac.compare_digest(otp.code_hash, _hash_code(phone, code)):
        otp.attempts += 1
        db.commit()  # keep the failed attempt even though we raise
        raise Unauthorized("Wrong code", code="otp_invalid")
    otp.used_at = now
    user = db.scalars(select(User).where(User.phone == phone)).first()
    if user is None:
        user = User(id=uuid.uuid4(), phone=phone)
        db.add(user)
        db.flush()
        ensure_user_accounts(db, user.id)
    return user


def issue_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(UTC)  # wall clock: the JWT library validates expiry against real time
    payload = {"sub": str(user.id), "role": user.role, "iat": now, "exp": now + timedelta(minutes=settings.jwt_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise Unauthorized("Sign in again") from exc

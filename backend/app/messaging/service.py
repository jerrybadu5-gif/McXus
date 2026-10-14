"""Messaging delivery service for MLS (RFC 9420). The server relays and stores opaque ciphertext only.

Flow for a new one-to-one chat (ADR 0008):
1. Every device publishes one-time KeyPackages (POST /v1/keys).
2. A opens a chat with B (POST /v1/conversations). The first time, A claims one of B's KeyPackages, creates an
   MLS group locally, adds B and uploads the Welcome (POST /v1/conversations/{id}/welcome). Only the first
   Welcome is accepted, so two phones starting the chat at the same moment cannot fork it.
3. Both sides send application messages (encrypted) and fetch them with /v1/messages/sync (long-poll).
4. Messages expire after MCXUS_MESSAGE_TTL_DAYS (30) and are deleted by the worker.
"""

import base64
import binascii
import time
import uuid
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import clock
from app.auth.service import normalise_phone
from app.config import get_settings
from app.errors import AppError, Conflict, NotFound
from app.models import Conversation, ConversationMember, Device, KeyPackage, Listing, MlsMessage, User


def decode_payload(b64: str) -> bytes:
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AppError("Payload must be base64", code="invalid_payload") from exc
    if not data:
        raise AppError("Empty payload", code="invalid_payload")
    if len(data) > get_settings().max_message_bytes:
        raise AppError("Message too large", code="payload_too_large")
    return data


def encode(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ---------- devices and key packages ----------


def register_device(db: Session, user: User, name: str) -> Device:
    """Register this phone. M3 supports one active device per user: unused KeyPackages of earlier devices (for
    example before a reinstall, whose keys are gone) are deleted so nobody starts a chat the user cannot read."""
    db.execute(delete(KeyPackage).where(KeyPackage.user_id == user.id, KeyPackage.claimed_at.is_(None)))
    device = Device(id=uuid.uuid4(), user_id=user.id, name=name[:60], last_seen_at=clock.now())
    db.add(device)
    db.flush()
    return device


def own_device(db: Session, user: User, device_id: uuid.UUID) -> Device:
    device = db.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise NotFound("Device not found")
    return device


def upload_key_packages(db: Session, user: User, device_id: uuid.UUID, packages: list[str]) -> int:
    device = own_device(db, user, device_id)
    limit = get_settings().max_key_packages_per_device
    if unclaimed_count(db, device.id) + len(packages) > limit:
        raise AppError(f"A device can hold at most {limit} unused key packages", code="too_many_key_packages")
    for b64 in packages:
        db.add(KeyPackage(user_id=user.id, device_id=device.id, data=decode_payload(b64)))
    db.flush()
    return unclaimed_count(db, device.id)


def unclaimed_count(db: Session, device_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(KeyPackage)
            .where(KeyPackage.device_id == device_id, KeyPackage.claimed_at.is_(None))
        )
        or 0
    )


def claim_key_package(db: Session, claimer: User, target_user_id: uuid.UUID) -> KeyPackage:
    """Hand out one unused KeyPackage of the target user (each is used once). SKIP LOCKED: concurrent claims
    never receive the same one."""
    if target_user_id == claimer.id:
        raise AppError("You cannot start a chat with yourself", code="self_chat")
    package = db.scalars(
        select(KeyPackage)
        .where(KeyPackage.user_id == target_user_id, KeyPackage.claimed_at.is_(None))
        .order_by(KeyPackage.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if package is None:
        raise Conflict("This person needs to open McXus once before you can message them", code="no_key_packages")
    package.claimed_at = clock.now()
    package.claimed_by = claimer.id
    return package


# ---------- people and conversations ----------


def lookup_user(db: Session, raw_phone: str) -> User:
    user = db.scalars(select(User).where(User.phone == normalise_phone(raw_phone), User.status == "active")).first()
    if user is None:
        raise NotFound("No McXus user has that number")
    return user


def _pair_key(a: uuid.UUID, b: uuid.UUID) -> str:
    return ":".join(sorted((a.hex, b.hex)))


def open_direct(db: Session, user: User, peer_id: uuid.UUID, listing_id: uuid.UUID | None) -> Conversation:
    """Return the one-to-one chat between the two users, creating it if needed (race-safe)."""
    if peer_id == user.id:
        raise AppError("You cannot start a chat with yourself", code="self_chat")
    peer = db.get(User, peer_id)
    if peer is None or peer.status != "active":
        raise NotFound("User not found")
    if listing_id is not None and db.get(Listing, listing_id) is None:
        raise NotFound("Listing not found")
    key = _pair_key(user.id, peer.id)
    db.execute(
        pg_insert(Conversation)
        .values(
            id=uuid.uuid4(),
            kind="direct",
            pair_key=key,
            created_by=user.id,
            listing_id=listing_id,
            created_at=clock.now(),
        )
        .on_conflict_do_nothing(index_elements=["pair_key"])
    )
    conversation = db.scalars(select(Conversation).where(Conversation.pair_key == key)).one()
    for member in (user.id, peer.id):
        db.execute(
            pg_insert(ConversationMember)
            .values(conversation_id=conversation.id, user_id=member, created_at=clock.now())
            .on_conflict_do_nothing()
        )
    if listing_id is not None and conversation.listing_id != listing_id:
        conversation.listing_id = listing_id  # most recent listing the chat was opened from
    db.flush()
    return conversation


def member_conversation(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    is_member = db.get(ConversationMember, (conversation_id, user.id)) is not None
    if conversation is None or not is_member:
        raise NotFound("Conversation not found")
    return conversation


def conversations_for(db: Session, user: User) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Conversation, ConversationMember.user_id)
        .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
        .where(
            Conversation.id.in_(
                select(ConversationMember.conversation_id).where(ConversationMember.user_id == user.id)
            ),
            ConversationMember.user_id != user.id,
        )
        .order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc())
    ).all()
    return [{"conversation": c, "peer_id": peer} for c, peer in rows]


# ---------- messages ----------


def _store(
    db: Session,
    user: User,
    device: Device,
    conversation: Conversation,
    kind: str,
    payload: bytes,
    recipient: uuid.UUID | None = None,
) -> MlsMessage:
    now = clock.now()
    message = MlsMessage(
        conversation_id=conversation.id,
        sender_user_id=user.id,
        sender_device_id=device.id,
        kind=kind,
        recipient_user_id=recipient,
        payload=payload,
        created_at=now,
        expires_at=now + timedelta(days=get_settings().message_ttl_days),
    )
    db.add(message)
    conversation.last_message_at = now
    device.last_seen_at = now
    db.flush()
    return message


def post_welcome(
    db: Session, user: User, device_id: uuid.UUID, conversation_id: uuid.UUID, recipient_id: uuid.UUID, payload_b64: str
) -> MlsMessage:
    device = own_device(db, user, device_id)
    conversation = member_conversation(db, user, conversation_id)
    if db.get(ConversationMember, (conversation.id, recipient_id)) is None or recipient_id == user.id:
        raise AppError("The Welcome must go to the other member", code="invalid_recipient")
    claimed = cast(
        CursorResult[Any],
        db.execute(
            update(Conversation)
            .where(Conversation.id == conversation.id, Conversation.mls_ready_by.is_(None))
            .values(mls_ready_by=user.id)
        ),
    ).rowcount
    if not claimed:
        raise Conflict(
            "The other phone already set up encryption for this chat; wait for its Welcome", code="already_initialised"
        )
    db.refresh(conversation)
    return _store(db, user, device, conversation, "welcome", decode_payload(payload_b64), recipient_id)


def post_message(
    db: Session, user: User, device_id: uuid.UUID, conversation_id: uuid.UUID, kind: str, payload_b64: str
) -> MlsMessage:
    if kind not in ("application", "commit"):
        raise AppError("kind must be application or commit", code="invalid_kind")
    device = own_device(db, user, device_id)
    conversation = member_conversation(db, user, conversation_id)
    if conversation.mls_ready_by is None:
        raise Conflict("Encryption is not set up for this chat yet", code="not_initialised")
    return _store(db, user, device, conversation, kind, decode_payload(payload_b64))


def _visible(user: User, after: int):  # type: ignore[no-untyped-def]
    mine = select(ConversationMember.conversation_id).where(ConversationMember.user_id == user.id)
    return (
        select(MlsMessage)
        .where(
            MlsMessage.id > after,
            MlsMessage.conversation_id.in_(mine),
            MlsMessage.expires_at > clock.now(),
            or_(MlsMessage.kind != "welcome", MlsMessage.recipient_user_id == user.id),
        )
        .order_by(MlsMessage.id)
    )


def sync(db: Session, user: User, after: int, limit: int, wait: int, sleep=time.sleep) -> list[MlsMessage]:  # type: ignore[no-untyped-def]
    """Messages after the cursor, oldest first. With `wait`, holds the request until something arrives (or
    the wait ends) so phones get messages quickly without push notifications."""
    wait = max(0, min(wait, get_settings().sync_max_wait_seconds))
    deadline = time.monotonic() + wait
    while True:
        rows = list(db.scalars(_visible(user, after).limit(limit)))
        if rows or time.monotonic() >= deadline:
            return rows
        db.rollback()  # end the snapshot so the next look sees new rows
        sleep(1)


def purge_expired(db: Session) -> int:
    result = cast(CursorResult[Any], db.execute(delete(MlsMessage).where(MlsMessage.expires_at <= clock.now())))
    return result.rowcount or 0

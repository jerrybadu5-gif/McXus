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
import json
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import clock
from app.auth.service import normalise_phone
from app.config import get_settings
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.marketplace import moderation
from app.models import Conversation, ConversationMember, Device, KeyPackage, Listing, MediaBlob, MlsMessage, User


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
    device = Device(
        id=uuid.uuid4(), user_id=user.id, name=name[:60], last_seen_at=clock.now(), activated_at=clock.now()
    )
    db.add(device)
    db.flush()
    return device


def activate_device(db: Session, user: User, device_id: uuid.UUID) -> Device:
    """The account was opened on this device: new chats are set up here from now on. Unused KeyPackages of the
    account's other devices are removed so nobody encrypts a new chat for a device the person is not using."""
    device = own_device(db, user, device_id)
    device.activated_at = clock.now()
    db.execute(
        delete(KeyPackage).where(
            KeyPackage.user_id == user.id, KeyPackage.device_id != device.id, KeyPackage.claimed_at.is_(None)
        )
    )
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


MAX_CLAIMS_PER_PEER_PER_DAY = 5


def claim_key_package(
    db: Session, claimer: User, target_user_id: uuid.UUID, group_id: uuid.UUID | None = None
) -> KeyPackage:
    """Hand out one unused KeyPackage of the target user (each is used once). SKIP LOCKED: concurrent claims
    never receive the same one.

    Anti-abuse: KeyPackages are a limited resource; anyone draining them would stop others from starting chats.
    So a claim needs an open, not-yet-encrypted chat between the two people, and at most 5 claims a day per pair."""
    if target_user_id == claimer.id:
        raise AppError("You cannot start a chat with yourself", code="self_chat")
    if group_id is not None:  # adding someone to a group: only that group's admins
        group = _group(db, claimer, group_id, admin=True)
        if _is_member(db, group.id, target_user_id):
            raise Conflict("Already in the group", code="already_member")
    else:
        pending = db.scalar(
            select(Conversation.id).where(
                Conversation.pair_key == _pair_key(claimer.id, target_user_id), Conversation.mls_ready_by.is_(None)
            )
        )
        if pending is None:
            raise Conflict("Open the chat first (or it is already set up)", code="no_pending_chat")
    recent = db.scalar(
        select(func.count())
        .select_from(KeyPackage)
        .where(
            KeyPackage.user_id == target_user_id,
            KeyPackage.claimed_by == claimer.id,
            KeyPackage.claimed_at > clock.now() - timedelta(days=1),
        )
    )
    if (recent or 0) >= MAX_CLAIMS_PER_PEER_PER_DAY:
        raise Conflict("Too many tries to set up this chat today; try again tomorrow", code="too_many_claims")
    package = db.scalars(
        select(KeyPackage)
        .join(Device, Device.id == KeyPackage.device_id)
        .where(KeyPackage.user_id == target_user_id, KeyPackage.claimed_at.is_(None))
        .order_by(Device.activated_at.desc().nulls_last(), KeyPackage.id)
        .limit(1)
        .with_for_update(of=KeyPackage, skip_locked=True)
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
    """My chats, newest activity first. Direct chats carry the other person; groups their size and my role."""
    mine = db.execute(
        select(Conversation, ConversationMember.role, ConversationMember.key_device_id)
        .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
        .where(ConversationMember.user_id == user.id)
        .order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc())
    ).all()
    ids = [c.id for c, _, _ in mine]
    others: dict[uuid.UUID, list[uuid.UUID]] = {}
    for conv_id, member in db.execute(
        select(ConversationMember.conversation_id, ConversationMember.user_id).where(
            ConversationMember.conversation_id.in_(ids), ConversationMember.user_id != user.id
        )
    ):
        others.setdefault(conv_id, []).append(member)
    rows = []
    for c, role, key_device in mine:
        peers = others.get(c.id, [])
        rows.append(
            {
                "conversation": c,
                "peer_id": peers[0] if c.kind == "direct" and peers else None,
                "member_count": len(peers) + 1,
                "role": role,
                "key_device_id": key_device,
            }
        )
    return rows


# ---------- messages ----------


def _store(
    db: Session,
    user: User,
    device: Device,
    conversation: Conversation,
    kind: str,
    payload: bytes,
    recipient: uuid.UUID | None = None,
    epoch: int | None = None,
) -> MlsMessage:
    now = clock.now()
    message = MlsMessage(
        epoch=epoch,
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


def _recipient_device(db: Session, user_id: uuid.UUID, device_id: uuid.UUID | None) -> uuid.UUID | None:
    if device_id is None:
        return None
    device = db.get(Device, device_id)
    if device is None or device.user_id != user_id:
        raise AppError("That device does not belong to that person", code="invalid_device")
    return device.id


def _set_key_device(db: Session, conversation_id: uuid.UUID, user_id: uuid.UUID, device_id: uuid.UUID | None) -> None:
    member = db.get(ConversationMember, (conversation_id, user_id))
    if member is not None and device_id is not None:
        member.key_device_id = device_id


def post_welcome(
    db: Session,
    user: User,
    device_id: uuid.UUID,
    conversation_id: uuid.UUID,
    recipient_id: uuid.UUID,
    payload_b64: str,
    recipient_device_id: uuid.UUID | None = None,
) -> MlsMessage:
    device = own_device(db, user, device_id)
    conversation = member_conversation(db, user, conversation_id)
    if conversation.kind != "direct":
        raise AppError("Group Welcomes are sent with the members you add", code="use_group_endpoint")
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
    target_device = _recipient_device(db, recipient_id, recipient_device_id)
    _set_key_device(db, conversation.id, user.id, device.id)
    _set_key_device(db, conversation.id, recipient_id, target_device)
    message = _store(db, user, device, conversation, "welcome", decode_payload(payload_b64), recipient_id)
    message.recipient_device_id = target_device
    return message


def post_message(
    db: Session, user: User, device_id: uuid.UUID, conversation_id: uuid.UUID, kind: str, payload_b64: str
) -> MlsMessage:
    if kind != "application":
        raise AppError("Only application messages here; group changes use the group endpoints", code="invalid_kind")
    device = own_device(db, user, device_id)
    conversation = member_conversation(db, user, conversation_id)
    if conversation.mls_ready_by is None:
        raise Conflict("Encryption is not set up for this chat yet", code="not_initialised")
    return _store(db, user, device, conversation, kind, decode_payload(payload_b64))


def _visible(user: User, after: int, device_id: uuid.UUID | None = None):  # type: ignore[no-untyped-def]
    mine = select(ConversationMember.conversation_id).where(ConversationMember.user_id == user.id)
    # A Welcome is for one person and, when the sender named it, for one of their devices only.
    my_welcome = MlsMessage.recipient_user_id == user.id
    if device_id is not None:
        my_welcome = my_welcome & (
            MlsMessage.recipient_device_id.is_(None) | (MlsMessage.recipient_device_id == device_id)
        )
    return (
        select(MlsMessage)
        .where(
            MlsMessage.id > after,
            MlsMessage.conversation_id.in_(mine),
            MlsMessage.expires_at > clock.now(),
            or_(MlsMessage.kind != "welcome", my_welcome),
        )
        .order_by(MlsMessage.id)
    )


def sync(  # type: ignore[no-untyped-def]
    db: Session, user: User, after: int, limit: int, wait: int, sleep=time.sleep, device_id: uuid.UUID | None = None
) -> list[MlsMessage]:
    """Messages after the cursor, oldest first. With `wait`, holds the request until something arrives (or
    the wait ends) so phones get messages quickly without push notifications."""
    wait = max(0, min(wait, get_settings().sync_max_wait_seconds))
    deadline = time.monotonic() + wait
    while True:
        rows = list(db.scalars(_visible(user, after, device_id).limit(limit)))
        if rows or time.monotonic() >= deadline:
            return rows
        db.rollback()  # end the snapshot so the next look sees new rows
        sleep(1)


def purge_expired(db: Session) -> int:
    result = cast(CursorResult[Any], db.execute(delete(MlsMessage).where(MlsMessage.expires_at <= clock.now())))
    return result.rowcount or 0


# ---------- groups (M3.2) ----------


def _is_member(db: Session, conversation_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return db.get(ConversationMember, (conversation_id, user_id)) is not None


def _group(db: Session, user: User, group_id: uuid.UUID, *, admin: bool = False, lock: bool = False) -> Conversation:
    stmt = select(Conversation).where(Conversation.id == group_id, Conversation.kind == "group")
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    group = db.scalars(stmt).first()
    me = db.get(ConversationMember, (group_id, user.id)) if group else None
    if group is None or me is None:
        raise NotFound("Group not found")
    if admin and me.role != "admin":
        raise Forbidden("Only group admins can do that")
    return group


def _event(db: Session, user: User, device: Device | None, group: Conversation, data: dict[str, Any]) -> MlsMessage:
    """A plain notice the server writes into the group (who joined or left). Contains no message content."""
    sender_device = device or db.scalars(select(Device).where(Device.user_id == user.id).limit(1)).first()
    if sender_device is None:
        raise AppError("Register this phone first", code="no_device")
    return _store(db, user, sender_device, group, "event", json.dumps(data).encode())


def create_group(db: Session, user: User, title: str, device_id: uuid.UUID | None = None) -> Conversation:
    """Create an empty group with me as admin. My phone creates the MLS group locally at epoch 0, then adds
    people with add_members."""
    title = title.strip()
    if not 1 <= len(title) <= 80:
        raise AppError("Group name must be 1-80 characters", code="invalid_title")
    moderation.check_listing_text(title, "")
    group = Conversation(id=uuid.uuid4(), kind="group", created_by=user.id, title=title, mls_ready_by=user.id, epoch=0)
    db.add(group)
    db.flush()
    key_device = own_device(db, user, device_id).id if device_id else None
    db.add(
        ConversationMember(
            conversation_id=group.id, user_id=user.id, role="admin", key_device_id=key_device, created_at=clock.now()
        )
    )
    db.flush()
    return group


def group_members(db: Session, user: User, group_id: uuid.UUID) -> list[ConversationMember]:
    _group(db, user, group_id)
    return list(
        db.scalars(
            select(ConversationMember)
            .where(ConversationMember.conversation_id == group_id)
            .order_by(ConversationMember.created_at)
        )
    )


def _accept_change(group: Conversation, epoch: int) -> None:
    """One change per epoch, in order, so every phone ends in the same state."""
    if epoch != group.epoch:
        raise Conflict("The group changed meanwhile; refresh and try again", code="stale_epoch")
    group.epoch += 1


def add_members(
    db: Session,
    user: User,
    device_id: uuid.UUID,
    group_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    epoch: int,
    commit_b64: str,
    welcome_b64: str,
    devices: dict[uuid.UUID, uuid.UUID] | None = None,
) -> tuple[MlsMessage, list[MlsMessage]]:
    """Returns the stored commit and one Welcome per new member."""
    device = own_device(db, user, device_id)
    group = _group(db, user, group_id, admin=True, lock=True)
    new = list(dict.fromkeys(u for u in user_ids if not _is_member(db, group.id, u)))
    if not new:
        raise AppError("Choose at least one new member", code="no_new_members")
    for uid in new:
        person = db.get(User, uid)
        if person is None or person.status != "active":
            raise NotFound("User not found")
    count = db.scalar(select(func.count()).where(ConversationMember.conversation_id == group.id)) or 0
    limit = get_settings().max_group_members
    if count + len(new) > limit:
        raise Conflict(f"A group can have at most {limit} members", code="group_full")
    commit, welcome = decode_payload(commit_b64), decode_payload(welcome_b64)
    _accept_change(group, epoch)
    welcomes = []
    me = db.get(ConversationMember, (group.id, user.id))
    if me is not None and me.key_device_id is None:
        me.key_device_id = device.id  # the admin's keys live on the phone making the change
    for uid in new:  # Welcomes first: a new member joins before it sees the change that added it
        target = _recipient_device(db, uid, (devices or {}).get(uid))
        db.add(
            ConversationMember(
                conversation_id=group.id, user_id=uid, role="member", key_device_id=target, created_at=clock.now()
            )
        )
        welcome_row = _store(db, user, device, group, "welcome", welcome, recipient=uid)
        welcome_row.recipient_device_id = target
        welcomes.append(welcome_row)
    message = _store(db, user, device, group, "commit", commit, epoch=epoch)
    _event(db, user, device, group, {"type": "added", "by": str(user.id), "users": [str(u) for u in new]})
    return message, welcomes


def remove_members(
    db: Session,
    user: User,
    device_id: uuid.UUID,
    group_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    epoch: int,
    commit_b64: str,
) -> MlsMessage:
    """Admins remove people (also used to complete someone's 'leave' in the encryption)."""
    device = own_device(db, user, device_id)
    group = _group(db, user, group_id, admin=True, lock=True)
    if user.id in user_ids:
        raise AppError("Use Leave group to remove yourself", code="use_leave")
    commit = decode_payload(commit_b64)
    _accept_change(group, epoch)
    removed = []
    for uid in user_ids:
        member = db.get(ConversationMember, (group.id, uid))
        if member is not None:
            db.delete(member)
            removed.append(str(uid))
    db.flush()
    message = _store(db, user, device, group, "commit", commit, epoch=epoch)
    if removed:
        _event(db, user, device, group, {"type": "removed", "by": str(user.id), "users": removed})
    return message


def leave_group(db: Session, user: User, group_id: uuid.UUID) -> None:
    """Stop receiving the group at once; an admin's phone then removes this person from the encryption."""
    group = _group(db, user, group_id, lock=True)
    db.delete(db.get(ConversationMember, (group.id, user.id)))
    db.flush()
    remaining = list(
        db.scalars(
            select(ConversationMember)
            .where(ConversationMember.conversation_id == group.id)
            .order_by(ConversationMember.created_at)
        )
    )
    if remaining and not any(m.role == "admin" for m in remaining):
        remaining[0].role = "admin"  # a group always keeps an admin
    if remaining:
        _event(db, user, None, group, {"type": "left", "users": [str(user.id)]})


def set_role(db: Session, user: User, group_id: uuid.UUID, target: uuid.UUID, role: str) -> None:
    if role not in ("admin", "member"):
        raise AppError("role must be admin or member", code="invalid_role")
    group = _group(db, user, group_id, admin=True)
    member = db.get(ConversationMember, (group.id, target))
    if member is None:
        raise NotFound("Not a member")
    member.role = role


def rename_group(db: Session, user: User, group_id: uuid.UUID, title: str) -> Conversation:
    group = _group(db, user, group_id, admin=True)
    title = title.strip()
    if not 1 <= len(title) <= 80:
        raise AppError("Group name must be 1-80 characters", code="invalid_title")
    moderation.check_listing_text(title, "")
    group.title = title
    return group


# ---------- encrypted media (photos, voice notes) ----------


def _blob_path(blob_id: uuid.UUID) -> Path:
    return Path(get_settings().blob_dir) / blob_id.hex[:2] / blob_id.hex


def save_blob(db: Session, user: User, conversation_id: uuid.UUID, data: bytes) -> MediaBlob:
    conversation = member_conversation(db, user, conversation_id)
    if not data:
        raise AppError("Empty file", code="invalid_payload")
    if len(data) > get_settings().max_blob_bytes:
        raise AppError("File too large", code="payload_too_large")
    now = clock.now()
    blob = MediaBlob(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        uploader_id=user.id,
        size=len(data),
        created_at=now,
        expires_at=now + timedelta(days=get_settings().message_ttl_days),
    )
    path = _blob_path(blob.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    db.add(blob)
    db.flush()
    return blob


def read_blob(db: Session, user: User, blob_id: uuid.UUID) -> bytes:
    blob = db.get(MediaBlob, blob_id)
    if blob is None or blob.expires_at <= clock.now() or not _is_member(db, blob.conversation_id, user.id):
        raise NotFound("File not found")
    try:
        return _blob_path(blob.id).read_bytes()
    except FileNotFoundError as exc:
        raise NotFound("File not found") from exc


def purge_expired_blobs(db: Session) -> int:
    expired = list(db.scalars(select(MediaBlob).where(MediaBlob.expires_at <= clock.now())))
    for blob in expired:
        _blob_path(blob.id).unlink(missing_ok=True)
        db.delete(blob)
    return len(expired)


# ---------- push ----------


def set_push_token(db: Session, user: User, device_id: uuid.UUID, token: str | None) -> None:
    own_device(db, user, device_id).push_token = token or None


def push_targets(db: Session, message: MlsMessage) -> list[str]:
    """Push tokens of the phones that should wake up for this message (never the sender's phone)."""
    recipients = (
        select(ConversationMember.user_id).where(ConversationMember.conversation_id == message.conversation_id)
        if message.recipient_user_id is None
        else select(User.id).where(User.id == message.recipient_user_id)
    )
    return list(
        db.scalars(
            select(Device.push_token).where(
                Device.user_id.in_(recipients),
                Device.id != message.sender_device_id,
                Device.push_token.is_not(None),
            )
        )
    )

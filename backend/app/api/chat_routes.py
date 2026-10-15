"""Messaging API (module M3). Bodies carry base64 MLS data; the server never sees message content."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import people, push
from app.api.market_schemas import SellerCard
from app.auth.deps import current_user
from app.config import get_settings
from app.db import get_db, get_sessionmaker
from app.errors import AppError
from app.marketplace import service as market
from app.messaging import service as chat
from app.messaging.service import encode
from app.models import Device, MlsMessage, User

router = APIRouter(prefix="/v1", tags=["messaging"])
DB = Annotated[Session, Depends(get_db)]
Me = Annotated[User, Depends(current_user)]
B64 = Annotated[str, Field(min_length=4, max_length=90_000, description="base64")]


class DeviceIn(BaseModel):
    name: str = Field(default="Android phone", max_length=60)


class DeviceOut(BaseModel):
    device_id: uuid.UUID


class KeyPackagesIn(BaseModel):
    device_id: uuid.UUID
    key_packages: list[B64] = Field(min_length=1, max_length=50)


class CountOut(BaseModel):
    unclaimed: int


class ClaimIn(BaseModel):
    user_id: uuid.UUID
    group_id: uuid.UUID | None = Field(default=None, description="Set when an admin adds this person to a group")


class ClaimOut(BaseModel):
    key_package: str
    device_id: uuid.UUID


class LookupIn(BaseModel):
    phone: str


class OpenIn(BaseModel):
    peer_user_id: uuid.UUID
    listing_id: uuid.UUID | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    kind: str
    peer: SellerCard | None = Field(description="Direct chats: the other person")
    title: str | None = Field(default=None, description="Groups: the group name")
    member_count: int = 2
    my_role: str = "member"
    keys_device_id: uuid.UUID | None = Field(default=None, description="Which of my devices holds this chat's keys")
    listing_id: uuid.UUID | None
    encryption_ready: bool
    started_by_me: bool
    last_message_at: datetime | None
    created_at: datetime


class WelcomeIn(BaseModel):
    device_id: uuid.UUID
    recipient_user_id: uuid.UUID
    recipient_device_id: uuid.UUID | None = Field(
        default=None, description="The device the claimed KeyPackage came from"
    )
    payload: B64


class MessageIn(BaseModel):
    device_id: uuid.UUID
    kind: Literal["application"] = "application"
    payload: B64


class MessageOut(BaseModel):
    id: int
    conversation_id: uuid.UUID
    sender_user_id: uuid.UUID
    sender_device_id: uuid.UUID
    kind: str
    payload: str
    epoch: int | None = None
    created_at: datetime


def _message(m: MlsMessage) -> MessageOut:
    return MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        sender_user_id=m.sender_user_id,
        sender_device_id=m.sender_device_id,
        kind=m.kind,
        payload=encode(m.payload),
        epoch=m.epoch,
        created_at=m.created_at,
    )


@router.post("/devices", status_code=201)
def register_device(body: DeviceIn, user: Me, db: DB) -> DeviceOut:
    device = chat.register_device(db, user, body.name)
    db.commit()
    return DeviceOut(device_id=device.id)


@router.post("/keys")
def upload_keys(body: KeyPackagesIn, user: Me, db: DB) -> CountOut:
    count = chat.upload_key_packages(db, user, body.device_id, body.key_packages)
    db.commit()
    return CountOut(unclaimed=count)


@router.get("/keys/count")
def key_count(device_id: uuid.UUID, user: Me, db: DB) -> CountOut:
    return CountOut(unclaimed=chat.unclaimed_count(db, chat.own_device(db, user, device_id).id))


@router.post("/keys/claim")
def claim_key(body: ClaimIn, user: Me, db: DB) -> ClaimOut:
    package = chat.claim_key_package(db, user, body.user_id, body.group_id)
    db.commit()
    return ClaimOut(key_package=encode(package.data), device_id=package.device_id)


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str
    phone_hint: str = Field(description="Last 3 digits of the phone, so people with the same name can be told apart")
    badge: str


@router.get("/users/search")
def search_people(user: Me, db: DB, q: str = "", limit: Annotated[int, Query(ge=1, le=20)] = 8) -> list[PersonOut]:
    """Suggestions as you type: names (any case, words in any order, from 2 letters) or a phone number (7+ digits)."""
    q = q.strip()
    condition = people.match(q, min_phone_digits=7)
    if condition is None or (len(q) < 2 and not q.isdigit()):
        return []
    found = list(
        db.scalars(
            select(User)
            .where(condition, User.status == "active", User.id != user.id)
            .order_by(User.display_name)
            .limit(limit)
        )
    )
    cards = market.seller_cards(db, {u.id for u in found})
    return [PersonOut(**people.card(u), badge=cards.get(u.id, {}).get("badge", "new_seller")) for u in found]


@router.post("/users/lookup")
def lookup(body: LookupIn, user: Me, db: DB) -> SellerCard:
    found = chat.lookup_user(db, body.phone)
    return SellerCard(**market.seller_cards(db, {found.id})[found.id])


def _out(db: Session, user: User, rows: list[dict]) -> list[ConversationOut]:  # type: ignore[type-arg]
    cards = market.seller_cards(db, {r["peer_id"] for r in rows if r["peer_id"]})
    return [
        ConversationOut(
            id=r["conversation"].id,
            kind=r["conversation"].kind,
            peer=SellerCard(**cards[r["peer_id"]]) if r["peer_id"] else None,
            title=r["conversation"].title,
            member_count=r.get("member_count", 2),
            my_role=r.get("role", "member"),
            keys_device_id=r.get("key_device_id"),
            listing_id=r["conversation"].listing_id,
            encryption_ready=r["conversation"].mls_ready_by is not None,
            started_by_me=r["conversation"].mls_ready_by == user.id,
            last_message_at=r["conversation"].last_message_at,
            created_at=r["conversation"].created_at,
        )
        for r in rows
    ]


def _wake(background: BackgroundTasks, db: Session, *messages: MlsMessage) -> None:
    """After commit: content-free pushes to the recipients' phones (no-op when Firebase is not set up)."""
    if push.client() is None:
        return
    tokens = [t for m in messages for t in chat.push_targets(db, m)]
    if tokens:
        background.add_task(_push_and_forget_dead, tokens)


def wake_users(background: BackgroundTasks, db: Session, user_ids: list[uuid.UUID]) -> None:
    """Content-free push to these people's phones so the app checks for news (e.g. a dispute update)."""
    if push.client() is None:
        return
    tokens = chat.user_push_tokens(db, user_ids)
    if tokens:
        background.add_task(_push_and_forget_dead, tokens)


def _push_and_forget_dead(tokens: list[str]) -> None:
    dead = push.notify(tokens)
    if dead:
        with get_sessionmaker()() as db:
            for device in db.query(Device).filter(Device.push_token.in_(dead)):
                device.push_token = None
            db.commit()


@router.post("/conversations")
def open_conversation(body: OpenIn, user: Me, db: DB) -> ConversationOut:
    conversation = chat.open_direct(db, user, body.peer_user_id, body.listing_id)
    db.commit()
    return _out(db, user, [{"conversation": conversation, "peer_id": body.peer_user_id}])[0]


@router.get("/conversations")
def list_conversations(user: Me, db: DB) -> list[ConversationOut]:
    return _out(db, user, chat.conversations_for(db, user))


@router.post("/conversations/{conversation_id}/welcome", status_code=201)
def welcome(conversation_id: uuid.UUID, body: WelcomeIn, user: Me, db: DB, bg: BackgroundTasks) -> MessageOut:
    message = chat.post_welcome(
        db, user, body.device_id, conversation_id, body.recipient_user_id, body.payload, body.recipient_device_id
    )
    db.commit()
    _wake(bg, db, message)
    return _message(message)


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def send(conversation_id: uuid.UUID, body: MessageIn, user: Me, db: DB, bg: BackgroundTasks) -> MessageOut:
    message = chat.post_message(db, user, body.device_id, conversation_id, body.kind, body.payload)
    db.commit()
    _wake(bg, db, message)
    return _message(message)


@router.get("/messages/sync")
def sync(
    user: Me,
    db: DB,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    wait: Annotated[int, Query(ge=0, le=60)] = 0,
    device_id: uuid.UUID | None = None,
) -> list[MessageOut]:
    """New messages for all my chats after `after` (a message id). `wait` (seconds) long-polls. With `device_id`,
    Welcomes meant for my other devices are left out."""
    return [_message(m) for m in chat.sync(db, user, after, limit, wait, device_id=device_id)]


@router.post("/devices/{device_id}/activate", status_code=204)
def activate(device_id: uuid.UUID, user: Me, db: DB) -> Response:
    """The account was opened on this device: set up new chats here (one device per account for now)."""
    chat.activate_device(db, user, device_id)
    db.commit()
    return Response(status_code=204)


# ---------- push ----------


class PushTokenIn(BaseModel):
    token: str | None = Field(default=None, max_length=512, description="Firebase token; null turns pushes off")


@router.post("/devices/{device_id}/push-token", status_code=204)
def push_token(device_id: uuid.UUID, body: PushTokenIn, user: Me, db: DB) -> Response:
    chat.set_push_token(db, user, device_id, body.token)
    db.commit()
    return Response(status_code=204)


# ---------- groups ----------


class GroupIn(BaseModel):
    title: str = Field(min_length=1, max_length=80, examples=["Eriku Youth Group"])
    device_id: uuid.UUID | None = Field(default=None, description="The creator's device (holds the group's keys)")


class MemberOut(BaseModel):
    user: SellerCard
    role: str


class GroupOut(BaseModel):
    id: uuid.UUID
    title: str | None
    epoch: int
    members: list[MemberOut]


class AddMembersIn(BaseModel):
    device_id: uuid.UUID
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=255)
    epoch: int = Field(ge=0, description="The group epoch the commit was made in")
    commit: B64
    welcome: B64
    devices: dict[uuid.UUID, uuid.UUID] = Field(default={}, description="user id -> device of the claimed KeyPackage")


class RemoveMembersIn(BaseModel):
    device_id: uuid.UUID
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=255)
    epoch: int = Field(ge=0)
    commit: B64


class RoleIn(BaseModel):
    user_id: uuid.UUID
    role: Literal["admin", "member"]


def _group_out(db: Session, user: User, group_id: uuid.UUID) -> GroupOut:
    members = chat.group_members(db, user, group_id)
    cards = market.seller_cards(db, {m.user_id for m in members})
    group = chat.member_conversation(db, user, group_id)
    return GroupOut(
        id=group.id,
        title=group.title,
        epoch=group.epoch,
        members=[MemberOut(user=SellerCard(**cards[m.user_id]), role=m.role) for m in members],
    )


@router.post("/groups", status_code=201)
def create_group(body: GroupIn, user: Me, db: DB) -> ConversationOut:
    """Create a group with me as admin; then add people (claim their KeyPackages with group_id, then
    POST /groups/{id}/members)."""
    group = chat.create_group(db, user, body.title, body.device_id)
    db.commit()
    return _out(db, user, [{"conversation": group, "peer_id": None, "member_count": 1, "role": "admin"}])[0]


@router.get("/groups/{group_id}")
def get_group(group_id: uuid.UUID, user: Me, db: DB) -> GroupOut:
    return _group_out(db, user, group_id)


@router.put("/groups/{group_id}")
def rename_group(group_id: uuid.UUID, body: GroupIn, user: Me, db: DB) -> GroupOut:
    chat.rename_group(db, user, group_id, body.title)
    db.commit()
    return _group_out(db, user, group_id)


@router.post("/groups/{group_id}/members")
def add_members(group_id: uuid.UUID, body: AddMembersIn, user: Me, db: DB, bg: BackgroundTasks) -> MessageOut:
    """Admin adds people: the MLS Commit (for current members) and Welcome (for the new ones). Refused with
    409 stale_epoch if the group changed since the commit was made."""
    message, welcomes = chat.add_members(
        db, user, body.device_id, group_id, body.user_ids, body.epoch, body.commit, body.welcome, body.devices
    )
    db.commit()
    _wake(bg, db, message, *welcomes)
    return _message(message)


@router.post("/groups/{group_id}/members/remove")
def remove_members(group_id: uuid.UUID, body: RemoveMembersIn, user: Me, db: DB, bg: BackgroundTasks) -> MessageOut:
    message = chat.remove_members(db, user, body.device_id, group_id, body.user_ids, body.epoch, body.commit)
    db.commit()
    _wake(bg, db, message)
    return _message(message)


@router.post("/groups/{group_id}/leave", status_code=204)
def leave(group_id: uuid.UUID, user: Me, db: DB) -> Response:
    chat.leave_group(db, user, group_id)
    db.commit()
    return Response(status_code=204)


@router.post("/groups/{group_id}/role", status_code=204)
def set_role(group_id: uuid.UUID, body: RoleIn, user: Me, db: DB) -> Response:
    chat.set_role(db, user, group_id, body.user_id, body.role)
    db.commit()
    return Response(status_code=204)


# ---------- encrypted media ----------


class BlobOut(BaseModel):
    id: uuid.UUID
    size: int


@router.post("/conversations/{conversation_id}/blobs", status_code=201)
async def upload_blob(conversation_id: uuid.UUID, request: Request, user: Me, db: DB) -> BlobOut:
    """Upload an encrypted photo or voice note (raw bytes, application/octet-stream, max 5 MB)."""
    limit = get_settings().max_blob_bytes
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise AppError("File too large", code="payload_too_large")
    blob = chat.save_blob(db, user, conversation_id, bytes(data))
    db.commit()
    return BlobOut(id=blob.id, size=blob.size)


@router.get("/blobs/{blob_id}")
def download_blob(blob_id: uuid.UUID, user: Me, db: DB) -> Response:
    return Response(
        content=chat.read_blob(db, user, blob_id),
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, max-age=86400"},
    )

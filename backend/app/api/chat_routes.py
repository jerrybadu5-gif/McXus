"""Messaging API (module M3). Bodies carry base64 MLS data; the server never sees message content."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.market_schemas import SellerCard
from app.auth.deps import current_user
from app.db import get_db
from app.marketplace import service as market
from app.messaging import service as chat
from app.messaging.service import encode
from app.models import MlsMessage, User

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
    peer: SellerCard
    listing_id: uuid.UUID | None
    encryption_ready: bool
    started_by_me: bool
    last_message_at: datetime | None
    created_at: datetime


class WelcomeIn(BaseModel):
    device_id: uuid.UUID
    recipient_user_id: uuid.UUID
    payload: B64


class MessageIn(BaseModel):
    device_id: uuid.UUID
    kind: Literal["application", "commit"] = "application"
    payload: B64


class MessageOut(BaseModel):
    id: int
    conversation_id: uuid.UUID
    sender_user_id: uuid.UUID
    sender_device_id: uuid.UUID
    kind: str
    payload: str
    created_at: datetime


def _message(m: MlsMessage) -> MessageOut:
    return MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        sender_user_id=m.sender_user_id,
        sender_device_id=m.sender_device_id,
        kind=m.kind,
        payload=encode(m.payload),
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
    package = chat.claim_key_package(db, user, body.user_id)
    db.commit()
    return ClaimOut(key_package=encode(package.data), device_id=package.device_id)


@router.post("/users/lookup")
def lookup(body: LookupIn, user: Me, db: DB) -> SellerCard:
    found = chat.lookup_user(db, body.phone)
    return SellerCard(**market.seller_cards(db, {found.id})[found.id])


def _out(db: Session, user: User, rows: list[dict]) -> list[ConversationOut]:  # type: ignore[type-arg]
    cards = market.seller_cards(db, {r["peer_id"] for r in rows})
    return [
        ConversationOut(
            id=r["conversation"].id,
            kind=r["conversation"].kind,
            peer=SellerCard(**cards[r["peer_id"]]),
            listing_id=r["conversation"].listing_id,
            encryption_ready=r["conversation"].mls_ready_by is not None,
            started_by_me=r["conversation"].mls_ready_by == user.id,
            last_message_at=r["conversation"].last_message_at,
            created_at=r["conversation"].created_at,
        )
        for r in rows
    ]


@router.post("/conversations")
def open_conversation(body: OpenIn, user: Me, db: DB) -> ConversationOut:
    conversation = chat.open_direct(db, user, body.peer_user_id, body.listing_id)
    db.commit()
    return _out(db, user, [{"conversation": conversation, "peer_id": body.peer_user_id}])[0]


@router.get("/conversations")
def list_conversations(user: Me, db: DB) -> list[ConversationOut]:
    return _out(db, user, chat.conversations_for(db, user))


@router.post("/conversations/{conversation_id}/welcome", status_code=201)
def welcome(conversation_id: uuid.UUID, body: WelcomeIn, user: Me, db: DB) -> MessageOut:
    message = chat.post_welcome(db, user, body.device_id, conversation_id, body.recipient_user_id, body.payload)
    db.commit()
    return _message(message)


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def send(conversation_id: uuid.UUID, body: MessageIn, user: Me, db: DB) -> MessageOut:
    message = chat.post_message(db, user, body.device_id, conversation_id, body.kind, body.payload)
    db.commit()
    return _message(message)


@router.get("/messages/sync")
def sync(
    user: Me,
    db: DB,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    wait: Annotated[int, Query(ge=0, le=60)] = 0,
) -> list[MessageOut]:
    """New messages for all my chats after `after` (a message id). `wait` (seconds) long-polls."""
    return [_message(m) for m in chat.sync(db, user, after, limit, wait)]

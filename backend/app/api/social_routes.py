"""Status, posts, comments, channels, the Discover feed and content moderation (M5, ADR 0012)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.api.market_routes import listing_cards
from app.api.market_schemas import ListingOut
from app.auth.deps import current_user, require_role
from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import Listing, User
from app.social import service as social

router = APIRouter(prefix="/v1")
DB = Annotated[Session, Depends(get_db)]
Me = Annotated[User, Depends(current_user)]
Moderator = Annotated[User, Depends(require_role("moderator"))]
Page = Annotated[int, Query(ge=1, le=50)]
Reason = Literal["prohibited", "scam", "wrong_category", "offensive", "other"]


class PersonOut(BaseModel):
    id: uuid.UUID | None
    name: str


async def _read(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError(f"Photos must be under {get_settings().max_upload_mb} MB", code="photo_too_large")
    return data


# ---------- status ----------


class StatusItemOut(BaseModel):
    id: uuid.UUID
    kind: Literal["text", "photo"]
    text: str
    color: str
    photo: str | None = Field(description="Photo URL (needs the same sign-in)")
    width: int | None
    height: int | None
    created_at: datetime
    expires_at: datetime
    seen: bool
    views: int | None = Field(description="How many people saw it (only on your own status)")


class StatusGroupOut(BaseModel):
    user: PersonOut
    items: list[StatusItemOut]
    all_seen: bool
    latest: datetime


class StatusBoardOut(BaseModel):
    mine: list[StatusItemOut]
    contacts: list[StatusGroupOut] = Field(description="People you chat with who have a status now; unseen first")


class TextStatusIn(BaseModel):
    text: str = Field(min_length=1, max_length=700)
    color: str = Field(default="#0B2545", pattern=r"^#[0-9A-Fa-f]{6}$")


class ViewerOut(BaseModel):
    user: PersonOut
    seen_at: datetime


class HiddenIn(BaseModel):
    user_ids: list[uuid.UUID] = Field(max_length=500)


@router.get("/status", tags=["status"])
def status_board(user: Me, db: DB) -> StatusBoardOut:
    """My status and the status of people I chat with (24 hours)."""
    return StatusBoardOut.model_validate(social.status_board(db, user))


@router.post("/status", status_code=201, tags=["status"])
def add_status(body: TextStatusIn, user: Me, db: DB) -> StatusItemOut:
    s = social.add_status(db, user, body.text, body.color)
    db.commit()
    return StatusItemOut.model_validate(social._status_item(s, True, 0))


@router.post("/status/photo", status_code=201, tags=["status"])
async def add_photo_status(user: Me, db: DB, file: UploadFile, caption: str = "") -> StatusItemOut:
    s = social.add_photo_status(db, user, await _read(file), caption)
    db.commit()
    return StatusItemOut.model_validate(social._status_item(s, True, 0))


@router.get("/status/hidden", tags=["status"])
def hidden(user: Me, db: DB) -> list[uuid.UUID]:
    """People who don't see my status."""
    return social.hidden_from(db, user)


@router.put("/status/hidden", tags=["status"])
def set_hidden(body: HiddenIn, user: Me, db: DB) -> list[uuid.UUID]:
    result = social.set_hidden(db, user, body.user_ids)
    db.commit()
    return result


@router.get("/status/{status_id}/photo", tags=["status"], response_class=Response)
def status_photo(status_id: uuid.UUID, user: Me, db: DB) -> Response:
    return Response(
        social.status_photo(db, user, status_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/status/{status_id}/seen", status_code=204, tags=["status"])
def seen(status_id: uuid.UUID, user: Me, db: DB) -> Response:
    social.mark_seen(db, user, status_id)
    db.commit()
    return Response(status_code=204)


@router.get("/status/{status_id}/viewers", tags=["status"])
def status_viewers(status_id: uuid.UUID, user: Me, db: DB) -> list[ViewerOut]:
    return [ViewerOut.model_validate(v) for v in social.viewers(db, user, status_id)]


@router.delete("/status/{status_id}", status_code=204, tags=["status"])
def delete_status(status_id: uuid.UUID, user: Me, db: DB) -> Response:
    social.delete_status(db, user, status_id)
    db.commit()
    return Response(status_code=204)


# ---------- posts and the feed ----------


class PhotoOut(BaseModel):
    url: str
    thumb_url: str
    width: int
    height: int


class ChannelRef(BaseModel):
    id: uuid.UUID
    name: str
    handle: str


class PostOut(BaseModel):
    type: Literal["post"] = "post"
    id: uuid.UUID
    author: PersonOut
    channel: ChannelRef | None
    text: str
    visibility: Literal["everyone", "contacts"]
    status: Literal["visible", "under_review", "removed", "deleted"]
    photos: list[PhotoOut]
    likes: int
    comments: int
    liked: bool
    mine: bool
    created_at: datetime


class FeedItem(BaseModel):
    type: Literal["post", "listing"]
    post: PostOut | None = None
    listing: ListingOut | None = None
    at: datetime


class FeedOut(BaseModel):
    items: list[FeedItem]
    next_before: datetime | None = Field(description="Pass as ?before= for the next page")


def _posts(db: Session, viewer: User, posts: list) -> list[PostOut]:  # type: ignore[type-arg]
    return [PostOut.model_validate(p) for p in social.post_views(db, viewer, posts)]


@router.get("/feed", tags=["posts"])
def feed(user: Me, db: DB, before: datetime | None = None, limit: Page = 20, listings: bool = True) -> FeedOut:
    """Discover: posts (public, my contacts', my channels') mixed with new listings, newest first."""
    posts = _posts(db, user, social.feed_posts(db, user, before, limit))
    items = [FeedItem(type="post", post=p, at=p.created_at) for p in posts]
    if listings:
        stmt = select(Listing).where(Listing.status == "active")
        if before is not None:
            stmt = stmt.where(Listing.created_at < before)
        rows = list(db.scalars(stmt.order_by(Listing.created_at.desc()).limit(limit)))
        items += [FeedItem(type="listing", listing=card, at=card.created_at) for card in listing_cards(db, rows)]
    items.sort(key=lambda i: i.at, reverse=True)
    items = items[:limit]
    return FeedOut(items=items, next_before=items[-1].at if len(items) == limit else None)


@router.post("/posts", status_code=201, tags=["posts"])
async def create_post(
    user: Me,
    db: DB,
    text: Annotated[str, Form(max_length=2000)] = "",
    visibility: Annotated[Literal["everyone", "contacts"], Form()] = "everyone",
    channel_id: Annotated[uuid.UUID | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File(description="Up to 4 photos")] = None,
) -> PostOut:
    """A post on Discover (or in a channel I run): text and/or up to 4 photos. Sent as multipart/form-data."""
    photos = [await _read(f) for f in (files or [])]
    post = social.create_post(db, user, text, visibility, channel_id, photos)
    db.commit()
    return _posts(db, user, [post])[0]


@router.get("/posts/{post_id}", tags=["posts"])
def get_post(post_id: uuid.UUID, user: Me, db: DB) -> PostOut:
    return _posts(db, user, [social.get_post(db, user, post_id)])[0]


@router.delete("/posts/{post_id}", status_code=204, tags=["posts"])
def delete_post(post_id: uuid.UUID, user: Me, db: DB) -> Response:
    social.delete_post(db, user, post_id)
    db.commit()
    return Response(status_code=204)


@router.get("/users/{user_id}/posts", tags=["posts"])
def user_posts(user_id: uuid.UUID, user: Me, db: DB, limit: Page = 20) -> list[PostOut]:
    return _posts(db, user, social.user_posts(db, user, user_id, limit))


@router.post("/posts/{post_id}/like", tags=["posts"])
def like(post_id: uuid.UUID, user: Me, db: DB) -> PostOut:
    post = social.like(db, user, post_id, True)
    db.commit()
    return _posts(db, user, [post])[0]


@router.delete("/posts/{post_id}/like", tags=["posts"])
def unlike(post_id: uuid.UUID, user: Me, db: DB) -> PostOut:
    post = social.like(db, user, post_id, False)
    db.commit()
    return _posts(db, user, [post])[0]


class CommentOut(BaseModel):
    id: uuid.UUID
    user: PersonOut
    text: str
    status: Literal["visible", "under_review", "removed", "deleted"]
    mine: bool
    can_delete: bool
    created_at: datetime


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.get("/posts/{post_id}/comments", tags=["posts"])
def list_comments(
    post_id: uuid.UUID,
    user: Me,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CommentOut]:
    return [CommentOut.model_validate(c) for c in social.comments(db, user, post_id, limit, offset)]


@router.post("/posts/{post_id}/comments", status_code=201, tags=["posts"])
def add_comment(post_id: uuid.UUID, body: CommentIn, user: Me, db: DB) -> list[CommentOut]:
    social.add_comment(db, user, post_id, body.text)
    db.commit()
    return [CommentOut.model_validate(c) for c in social.comments(db, user, post_id, 200, 0)]


@router.delete("/comments/{comment_id}", status_code=204, tags=["posts"])
def delete_comment(comment_id: uuid.UUID, user: Me, db: DB) -> Response:
    social.delete_comment(db, user, comment_id)
    db.commit()
    return Response(status_code=204)


class ContentReportIn(BaseModel):
    target_type: Literal["post", "comment", "channel"]
    target_id: uuid.UUID
    reason: Reason
    note: str = Field(default="", max_length=500)


@router.post("/reports", status_code=201, tags=["posts"])
def report(body: ContentReportIn, user: Me, db: DB) -> dict[str, str]:
    """Report a post, comment or channel. Three reports hide a post or comment until a moderator decides."""
    social.report(db, user, body.target_type, body.target_id, body.reason, body.note)
    db.commit()
    return {"status": "received"}


# ---------- channels ----------


class ChannelOut(BaseModel):
    id: uuid.UUID
    handle: str
    name: str
    description: str
    status: Literal["active", "suspended"]
    followers: int
    owner: PersonOut
    following: bool
    role: Literal["owner", "admin"] | None
    created_at: datetime


class ChannelIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    handle: str = Field(min_length=3, max_length=31, description="Short unique name, e.g. eriku-youth")
    description: str = Field(default="", max_length=500)


class ChannelEditIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=500)


class AdminIn(BaseModel):
    user_id: uuid.UUID
    admin: bool = True


def _channel_out(db: Session, user: User, channel_id: uuid.UUID) -> ChannelOut:
    channel = social._channel(db, channel_id, user)
    return ChannelOut.model_validate(social.channel_view(db, user, [channel])[0])


@router.post("/channels", status_code=201, tags=["channels"])
def create_channel(body: ChannelIn, user: Me, db: DB) -> ChannelOut:
    """Start a channel (verified accounts, level 2+). You and the admins you choose post; followers read."""
    channel = social.create_channel(db, user, body.name, body.handle, body.description)
    db.commit()
    return _channel_out(db, user, channel.id)


@router.get("/channels", tags=["channels"])
def find_channels(user: Me, db: DB, q: Annotated[str, Query(max_length=60)] = "", limit: Page = 20) -> list[ChannelOut]:
    """Search channels by name or handle (any case), or the most followed."""
    return [ChannelOut.model_validate(c) for c in social.find_channels(db, user, q, limit)]


@router.get("/channels/mine", tags=["channels"])
def my_channels(user: Me, db: DB) -> list[ChannelOut]:
    """Channels I follow (including the ones I run)."""
    return [ChannelOut.model_validate(c) for c in social.my_channels(db, user)]


@router.get("/channels/{channel_id}", tags=["channels"])
def get_channel(channel_id: uuid.UUID, user: Me, db: DB) -> ChannelOut:
    return _channel_out(db, user, channel_id)


@router.put("/channels/{channel_id}", tags=["channels"])
def edit_channel(channel_id: uuid.UUID, body: ChannelEditIn, user: Me, db: DB) -> ChannelOut:
    social.update_channel(db, user, channel_id, body.name, body.description)
    db.commit()
    return _channel_out(db, user, channel_id)


@router.get("/channels/{channel_id}/posts", tags=["channels"])
def channel_posts(
    channel_id: uuid.UUID, user: Me, db: DB, before: datetime | None = None, limit: Page = 20
) -> list[PostOut]:
    return _posts(db, user, social.channel_posts(db, user, channel_id, before, limit))


@router.post("/channels/{channel_id}/follow", tags=["channels"])
def follow(channel_id: uuid.UUID, user: Me, db: DB) -> ChannelOut:
    social.follow(db, user, channel_id, True)
    db.commit()
    return _channel_out(db, user, channel_id)


@router.delete("/channels/{channel_id}/follow", tags=["channels"])
def unfollow(channel_id: uuid.UUID, user: Me, db: DB) -> ChannelOut:
    social.follow(db, user, channel_id, False)
    db.commit()
    return _channel_out(db, user, channel_id)


@router.post("/channels/{channel_id}/admins", tags=["channels"])
def set_admin(channel_id: uuid.UUID, body: AdminIn, user: Me, db: DB) -> ChannelOut:
    """The owner adds or removes an admin (admins can post)."""
    social.set_admin(db, user, channel_id, body.user_id, body.admin)
    db.commit()
    return _channel_out(db, user, channel_id)


# ---------- moderation ----------


class ReportedOut(BaseModel):
    target_type: Literal["post", "comment", "channel"]
    target_id: uuid.UUID
    reports: int
    first_at: datetime
    reasons: list[str]
    notes: list[str]
    content: dict[str, object]


class ModerateIn(BaseModel):
    action: Literal["remove", "restore"]


@router.get("/mod/content-reports", tags=["moderation"])
def content_reports(staff: Moderator, db: DB, limit: Annotated[int, Query(ge=1, le=200)] = 100) -> list[ReportedOut]:
    """Reported posts, comments and channels, most reported first."""
    return [ReportedOut.model_validate(r) for r in social.report_queue(db, limit)]


@router.post("/mod/content/{target_type}/{target_id}/decision", tags=["moderation"])
def moderate(
    target_type: Literal["post", "comment", "channel"], target_id: uuid.UUID, body: ModerateIn, staff: Moderator, db: DB
) -> dict[str, str]:
    """Remove (a channel is suspended) or restore and dismiss the reports."""
    social.moderate(db, staff, target_type, target_id, body.action)
    audit.record(db, staff, f"{target_type}_{body.action}", target_type, target_id)
    db.commit()
    return {"status": body.action}

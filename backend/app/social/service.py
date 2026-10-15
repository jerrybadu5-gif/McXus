"""Status, posts, likes, comments, channels and their moderation (M5, ADR 0012).

Who sees what:
- Status (24 h): the people you have a direct chat with ("contacts"), minus anyone you hid it from.
- Posts: everyone (Discover), or contacts only if the author chooses. Channel posts: anyone can open the channel;
  the feed shows them to followers.
- Removed, deleted or under-review content is shown only to its author (and staff).
Nothing here is end-to-end encrypted (unlike chats); the app says so where people post.
"""

import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, false, func, or_, select, update
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.marketplace import media
from app.models import (
    Channel,
    ChannelAdmin,
    ChannelFollow,
    ContentReport,
    Conversation,
    ConversationMember,
    Post,
    PostComment,
    PostLike,
    PostPhoto,
    Status,
    StatusHide,
    StatusView,
    User,
)

STAFF_VIEW = ("support", "moderator", "compliance", "admin")
HANDLE = re.compile(r"^[a-z0-9][a-z0-9-]{2,29}$")
COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ---------- helpers ----------


def contact_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """People I have a one-to-one chat with."""
    mine = ConversationMember.__table__.alias("mine")
    other = ConversationMember.__table__.alias("other")
    rows = db.execute(
        select(other.c.user_id)
        .select_from(mine)
        .join(Conversation, Conversation.id == mine.c.conversation_id)
        .join(other, other.c.conversation_id == mine.c.conversation_id)
        .where(mine.c.user_id == user_id, other.c.user_id != user_id, Conversation.kind == "direct")
    )
    return {r[0] for r in rows}


def _text(value: str, what: str, limit: int, required: bool = True) -> str:
    value = value.strip()
    if required and not value:
        raise AppError(f"Write the {what}", code="text_required")
    if len(value) > limit:
        raise AppError(f"Keep the {what} under {limit} characters", code="too_long")
    return value


def _daily(db: Session, model: Any, user_col: Any, user_id: uuid.UUID, limit: int, what: str) -> None:
    since = clock.now() - timedelta(days=1)
    count = db.scalar(select(func.count()).select_from(model).where(user_col == user_id, model.created_at >= since))
    if (count or 0) >= limit:
        raise Conflict(f"You can add up to {limit} {what} a day", code="daily_limit")


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}


def _person(user: User | None) -> dict[str, Any]:
    if user is None:
        return {"id": None, "name": "McXus user"}
    return {"id": user.id, "name": user.store_name or user.display_name or "McXus user"}


# ---------- status ----------


def _status_storage() -> media.LocalStorage:
    return media.LocalStorage(get_settings().status_dir)


def add_status(db: Session, user: User, text: str, color: str) -> Status:
    settings = get_settings()
    _daily(db, Status, Status.user_id, user.id, settings.statuses_per_day, "status updates")
    if not COLOR.match(color):
        raise AppError("Pick a colour", code="color_invalid")
    now = clock.now()
    status = Status(
        id=uuid.uuid4(),
        user_id=user.id,
        kind="text",
        text=_text(text, "status", 700),
        color=color.upper(),
        created_at=now,
        expires_at=now + timedelta(hours=settings.status_hours),
    )
    db.add(status)
    db.flush()
    return status


def add_photo_status(db: Session, user: User, data: bytes, caption: str) -> Status:
    settings = get_settings()
    _daily(db, Status, Status.user_id, user.id, settings.statuses_per_day, "status updates")
    photo = media.process(data)
    status_id = uuid.uuid4()
    key = f"{user.id}/{status_id}.jpg"
    _status_storage().save(key, photo.full)
    now = clock.now()
    status = Status(
        id=status_id,
        user_id=user.id,
        kind="photo",
        text=_text(caption, "caption", 300, required=False),
        photo_key=key,
        width=photo.width,
        height=photo.height,
        created_at=now,
        expires_at=now + timedelta(hours=settings.status_hours),
    )
    db.add(status)
    db.flush()
    return status


def _can_see_status(db: Session, viewer: User, status: Status) -> bool:
    if status.user_id == viewer.id or viewer.role in STAFF_VIEW:
        return True
    if status.expires_at <= clock.now():
        return False
    if viewer.id not in contact_ids(db, status.user_id):
        return False
    return db.get(StatusHide, (status.user_id, viewer.id)) is None


def get_status(db: Session, viewer: User, status_id: uuid.UUID) -> Status:
    status = db.get(Status, status_id)
    if status is None or not _can_see_status(db, viewer, status):
        raise NotFound("Status not found")
    return status


def status_photo(db: Session, viewer: User, status_id: uuid.UUID) -> bytes:
    status = get_status(db, viewer, status_id)
    path = Path(get_settings().status_dir) / (status.photo_key or "-")
    if not status.photo_key or not path.is_file():
        raise NotFound("Photo not found")
    return path.read_bytes()


def mark_seen(db: Session, viewer: User, status_id: uuid.UUID) -> None:
    status = get_status(db, viewer, status_id)
    if status.user_id == viewer.id or db.get(StatusView, (status.id, viewer.id)) is not None:
        return
    db.add(StatusView(status_id=status.id, viewer_id=viewer.id, seen_at=clock.now()))


def _status_item(s: Status, seen: bool, views: int | None) -> dict[str, Any]:
    return {
        "id": s.id,
        "kind": s.kind,
        "text": s.text,
        "color": s.color,
        "photo": f"/v1/status/{s.id}/photo" if s.photo_key else None,
        "width": s.width,
        "height": s.height,
        "created_at": s.created_at,
        "expires_at": s.expires_at,
        "seen": seen,
        "views": views,
    }


def status_board(db: Session, user: User) -> dict[str, Any]:
    """My statuses (with view counts) and my contacts' current statuses, unseen first."""
    now = clock.now()
    contacts = contact_ids(db, user.id)
    hidden_from_me = set(db.scalars(select(StatusHide.owner_id).where(StatusHide.hidden_id == user.id)))
    owners = (contacts - hidden_from_me) | {user.id}
    rows = list(
        db.scalars(
            select(Status).where(Status.user_id.in_(owners), Status.expires_at > now).order_by(Status.created_at)
        )
    )
    ids = [s.id for s in rows]
    seen = (
        set(
            db.scalars(
                select(StatusView.status_id).where(StatusView.viewer_id == user.id, StatusView.status_id.in_(ids))
            )
        )
        if ids
        else set()
    )
    counts = (
        dict(
            db.execute(
                select(StatusView.status_id, func.count())
                .where(StatusView.status_id.in_(ids))
                .group_by(StatusView.status_id)
            ).all()
        )
        if ids
        else {}
    )
    people = _names(db, {s.user_id for s in rows})
    mine = [_status_item(s, True, counts.get(s.id, 0)) for s in rows if s.user_id == user.id]
    groups: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for s in rows:
        if s.user_id != user.id:
            groups.setdefault(s.user_id, []).append(_status_item(s, s.id in seen, None))
    others = [
        {
            "user": _person(people.get(uid)),
            "items": items,
            "all_seen": all(i["seen"] for i in items),
            "latest": items[-1]["created_at"],
        }
        for uid, items in groups.items()
    ]
    others.sort(key=lambda g: (g["all_seen"], -g["latest"].timestamp()))
    return {"mine": mine, "contacts": others}


def viewers(db: Session, owner: User, status_id: uuid.UUID) -> list[dict[str, Any]]:
    status = db.get(Status, status_id)
    if status is None or status.user_id != owner.id:
        raise NotFound("Status not found")
    rows = db.execute(
        select(StatusView, User)
        .join(User, User.id == StatusView.viewer_id)
        .where(StatusView.status_id == status_id)
        .order_by(StatusView.seen_at.desc())
    ).all()
    return [{"user": _person(u), "seen_at": v.seen_at} for v, u in rows]


def delete_status(db: Session, owner: User, status_id: uuid.UUID) -> None:
    status = db.get(Status, status_id)
    if status is None or status.user_id != owner.id:
        raise NotFound("Status not found")
    _drop_status(db, status)


def _drop_status(db: Session, status: Status) -> None:
    if status.photo_key:
        _status_storage().delete(status.photo_key)
    db.execute(delete(StatusView).where(StatusView.status_id == status.id))
    db.delete(status)


def hidden_from(db: Session, owner: User) -> list[uuid.UUID]:
    return list(db.scalars(select(StatusHide.hidden_id).where(StatusHide.owner_id == owner.id)))


def set_hidden(db: Session, owner: User, user_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    db.execute(delete(StatusHide).where(StatusHide.owner_id == owner.id))
    for uid in set(user_ids) - {owner.id}:
        db.add(StatusHide(owner_id=owner.id, hidden_id=uid))
    db.flush()
    return hidden_from(db, owner)


def purge_expired_statuses(db: Session) -> int:
    expired = list(db.scalars(select(Status).where(Status.expires_at <= clock.now()).limit(1000)))
    for status in expired:
        _drop_status(db, status)
    return len(expired)


# ---------- channels ----------


def _channel(db: Session, channel_id: uuid.UUID, viewer: User | None = None, *, lock: bool = False) -> Channel:
    channel = db.get(Channel, channel_id, with_for_update=lock)
    staff = viewer is not None and viewer.role in STAFF_VIEW
    if channel is None or (
        channel.status != "active" and not staff and (viewer is None or viewer.id != channel.owner_id)
    ):
        raise NotFound("Channel not found")
    return channel


def is_channel_admin(db: Session, channel: Channel, user: User) -> bool:
    return channel.owner_id == user.id or db.get(ChannelAdmin, (channel.id, user.id)) is not None


def create_channel(db: Session, owner: User, name: str, handle: str, description: str) -> Channel:
    if owner.kyc_tier < 2:
        raise Forbidden("Verify your account (level 2) to start a channel", code="kyc_required")
    owned = db.scalar(select(func.count()).select_from(Channel).where(Channel.owner_id == owner.id)) or 0
    if owned >= get_settings().channels_per_user:
        raise Conflict(f"You can own up to {get_settings().channels_per_user} channels", code="too_many_channels")
    handle = handle.strip().lower().lstrip("@")
    if not HANDLE.match(handle):
        raise AppError("The handle needs 3–30 letters, numbers or dashes", code="handle_invalid")
    if db.scalar(select(Channel.id).where(Channel.handle == handle)):
        raise Conflict("That handle is taken", code="handle_taken")
    channel = Channel(
        id=uuid.uuid4(),
        handle=handle,
        name=_text(name, "channel name", 60),
        description=_text(description, "description", 500, required=False),
        owner_id=owner.id,
        created_at=clock.now(),
        followers=1,
    )
    db.add(channel)
    db.flush()
    db.add(ChannelFollow(channel_id=channel.id, user_id=owner.id, created_at=clock.now()))
    return channel


def update_channel(db: Session, user: User, channel_id: uuid.UUID, name: str, description: str) -> Channel:
    channel = _channel(db, channel_id, user, lock=True)
    if channel.owner_id != user.id:
        raise Forbidden("Only the owner can edit the channel")
    channel.name = _text(name, "channel name", 60)
    channel.description = _text(description, "description", 500, required=False)
    return channel


def set_admin(db: Session, owner: User, channel_id: uuid.UUID, user_id: uuid.UUID, admin: bool) -> None:
    channel = _channel(db, channel_id, owner, lock=True)
    if channel.owner_id != owner.id:
        raise Forbidden("Only the owner can choose admins")
    if user_id == owner.id:
        raise AppError("You are the owner", code="own_account")
    current = db.get(ChannelAdmin, (channel.id, user_id))
    if admin and current is None:
        if db.get(User, user_id) is None:
            raise NotFound("User not found")
        db.add(ChannelAdmin(channel_id=channel.id, user_id=user_id))
    elif not admin and current is not None:
        db.delete(current)


def follow(db: Session, user: User, channel_id: uuid.UUID, on: bool) -> Channel:
    channel = _channel(db, channel_id, user, lock=True)
    current = db.get(ChannelFollow, (channel.id, user.id))
    if on and current is None:
        db.add(ChannelFollow(channel_id=channel.id, user_id=user.id, created_at=clock.now()))
        channel.followers += 1
    elif not on and current is not None:
        if channel.owner_id == user.id:
            raise AppError("The owner always follows their channel", code="owner_follows")
        db.delete(current)
        channel.followers = max(0, channel.followers - 1)
    return channel


def channel_view(db: Session, viewer: User, channels: list[Channel]) -> list[dict[str, Any]]:
    ids = [c.id for c in channels]
    following = (
        set(
            db.scalars(
                select(ChannelFollow.channel_id).where(
                    ChannelFollow.user_id == viewer.id, ChannelFollow.channel_id.in_(ids)
                )
            )
        )
        if ids
        else set()
    )
    admin_of = (
        set(
            db.scalars(
                select(ChannelAdmin.channel_id).where(
                    ChannelAdmin.user_id == viewer.id, ChannelAdmin.channel_id.in_(ids)
                )
            )
        )
        if ids
        else set()
    )
    owners = _names(db, {c.owner_id for c in channels})
    return [
        {
            "id": c.id,
            "handle": c.handle,
            "name": c.name,
            "description": c.description,
            "status": c.status,
            "followers": c.followers,
            "owner": _person(owners.get(c.owner_id)),
            "following": c.id in following,
            "role": "owner" if c.owner_id == viewer.id else "admin" if c.id in admin_of else None,
            "created_at": c.created_at,
        }
        for c in channels
    ]


def find_channels(db: Session, viewer: User, q: str, limit: int) -> list[dict[str, Any]]:
    """Search by name or handle (any case, words in any order), or the most followed when q is empty."""
    stmt = select(Channel).where(Channel.status == "active")
    words = [w for w in re.split(r"\s+", q.strip().lower().lstrip("@")) if w]
    for w in words:
        like = f"%{w.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(Channel.name.ilike(like), Channel.handle.ilike(like)))
    rows = list(db.scalars(stmt.order_by(Channel.followers.desc(), Channel.created_at.desc()).limit(limit)))
    return channel_view(db, viewer, rows)


def my_channels(db: Session, viewer: User) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(Channel)
            .join(ChannelFollow, ChannelFollow.channel_id == Channel.id)
            .where(ChannelFollow.user_id == viewer.id, or_(Channel.status == "active", Channel.owner_id == viewer.id))
            .order_by(Channel.name)
        )
    )
    return channel_view(db, viewer, rows)


# ---------- posts ----------


def create_post(
    db: Session, user: User, text: str, visibility: str, channel_id: uuid.UUID | None, photos: list[bytes]
) -> Post:
    settings = get_settings()
    if channel_id is None and user.kyc_tier < 1:
        raise Forbidden("Add your name and photo (level 1) to post on Discover", code="kyc_required")
    _daily(db, Post, Post.author_id, user.id, settings.posts_per_day, "posts")
    if len(photos) > settings.max_post_photos:
        raise AppError(f"Up to {settings.max_post_photos} photos per post", code="too_many_photos")
    text = _text(text, "post", 2000, required=not photos)
    if channel_id is not None:
        channel = _channel(db, channel_id, user)
        if channel.status != "active":
            raise Conflict("This channel is suspended", code="channel_suspended")
        if not is_channel_admin(db, channel, user):
            raise Forbidden("Only the channel's owner and admins can post")
        visibility = "everyone"
    if visibility not in ("everyone", "contacts"):
        raise AppError("Choose who sees the post", code="visibility_invalid")
    processed = [media.process(p) for p in photos]  # validates and strips metadata before anything is saved
    post = Post(
        id=uuid.uuid4(),
        author_id=user.id,
        channel_id=channel_id,
        text=text,
        visibility=visibility,
        created_at=clock.now(),
    )
    db.add(post)
    db.flush()
    store = media.storage()
    for i, photo in enumerate(processed):
        key = f"posts/{post.id}/{uuid.uuid4().hex}"
        store.save(f"{key}.jpg", photo.full)
        store.save(f"{key}_t.jpg", photo.thumb)
        db.add(PostPhoto(id=uuid.uuid4(), post_id=post.id, key=key, width=photo.width, height=photo.height, position=i))
    db.flush()
    return post


def _can_see_post(db: Session, viewer: User | None, post: Post, contacts: set[uuid.UUID] | None = None) -> bool:
    if viewer is not None and (viewer.id == post.author_id or viewer.role in STAFF_VIEW):
        return post.status != "deleted" or viewer.role in STAFF_VIEW
    if post.status != "visible":
        return False
    if post.channel_id is not None:
        channel = db.get(Channel, post.channel_id)
        return channel is not None and channel.status == "active"
    if post.visibility == "everyone":
        return True
    if viewer is None:
        return False
    contacts = contacts if contacts is not None else contact_ids(db, post.author_id)
    return viewer.id in contacts if contacts is not None else False


def get_post(db: Session, viewer: User | None, post_id: uuid.UUID, *, lock: bool = False) -> Post:
    post = db.get(Post, post_id, with_for_update=lock)
    if post is None or not _can_see_post(db, viewer, post):
        raise NotFound("Post not found")
    return post


def delete_post(db: Session, user: User, post_id: uuid.UUID) -> None:
    post = get_post(db, user, post_id, lock=True)
    allowed = post.author_id == user.id
    if not allowed and post.channel_id is not None:
        allowed = is_channel_admin(db, db.get(Channel, post.channel_id), user)  # type: ignore[arg-type]
    if not allowed:
        raise Forbidden("Only the author can delete this post")
    post.status = "deleted"


def like(db: Session, user: User, post_id: uuid.UUID, on: bool) -> Post:
    post = get_post(db, user, post_id, lock=True)
    current = db.get(PostLike, (post.id, user.id))
    if on and current is None:
        db.add(PostLike(post_id=post.id, user_id=user.id, created_at=clock.now()))
        post.likes += 1
    elif not on and current is not None:
        db.delete(current)
        post.likes = max(0, post.likes - 1)
    return post


def add_comment(db: Session, user: User, post_id: uuid.UUID, text: str) -> PostComment:
    post = get_post(db, user, post_id, lock=True)
    if post.status != "visible":
        raise Conflict("Comments are closed on this post", code="post_closed")
    _daily(db, PostComment, PostComment.user_id, user.id, get_settings().comments_per_day, "comments")
    comment = PostComment(
        id=uuid.uuid4(), post_id=post.id, user_id=user.id, text=_text(text, "comment", 500), created_at=clock.now()
    )
    db.add(comment)
    post.comments += 1
    db.flush()
    return comment


def delete_comment(db: Session, user: User, comment_id: uuid.UUID) -> None:
    comment = db.get(PostComment, comment_id, with_for_update=True)
    if comment is None or comment.status == "deleted":
        raise NotFound("Comment not found")
    post = db.get(Post, comment.post_id, with_for_update=True)
    assert post is not None
    if user.id not in (comment.user_id, post.author_id):
        raise Forbidden("Only the writer or the post's author can delete a comment")
    if comment.status == "visible":
        post.comments = max(0, post.comments - 1)
    comment.status = "deleted"


def comments(db: Session, viewer: User, post_id: uuid.UUID, limit: int, offset: int) -> list[dict[str, Any]]:
    post = get_post(db, viewer, post_id)
    staff = viewer.role in STAFF_VIEW
    stmt = select(PostComment).where(PostComment.post_id == post.id)
    if not staff:
        stmt = stmt.where(
            or_(
                PostComment.status == "visible",
                and_(PostComment.user_id == viewer.id, PostComment.status == "under_review"),
            )
        )
    rows = list(db.scalars(stmt.order_by(PostComment.created_at).limit(limit).offset(offset)))
    people = _names(db, {c.user_id for c in rows})
    return [
        {
            "id": c.id,
            "user": _person(people.get(c.user_id)),
            "text": c.text,
            "status": c.status,
            "mine": c.user_id == viewer.id,
            "can_delete": viewer.id in (c.user_id, post.author_id),
            "created_at": c.created_at,
        }
        for c in rows
    ]


def post_views(db: Session, viewer: User | None, posts: list[Post]) -> list[dict[str, Any]]:
    if not posts:
        return []
    ids = [p.id for p in posts]
    photos: dict[uuid.UUID, list[PostPhoto]] = {}
    for ph in db.scalars(select(PostPhoto).where(PostPhoto.post_id.in_(ids)).order_by(PostPhoto.position)):
        photos.setdefault(ph.post_id, []).append(ph)
    liked = (
        set(db.scalars(select(PostLike.post_id).where(PostLike.user_id == viewer.id, PostLike.post_id.in_(ids))))
        if viewer
        else set()
    )
    people = _names(db, {p.author_id for p in posts})
    channels = {
        c.id: c
        for c in db.scalars(select(Channel).where(Channel.id.in_({p.channel_id for p in posts if p.channel_id})))
    }
    out = []
    for p in posts:
        c = channels.get(p.channel_id) if p.channel_id else None
        out.append(
            {
                "type": "post",
                "id": p.id,
                "author": _person(people.get(p.author_id)),
                "channel": {"id": c.id, "name": c.name, "handle": c.handle} if c else None,
                "text": p.text,
                "visibility": p.visibility,
                "status": p.status,
                "photos": [
                    {
                        "url": media.url(f"{ph.key}.jpg"),
                        "thumb_url": media.url(f"{ph.key}_t.jpg"),
                        "width": ph.width,
                        "height": ph.height,
                    }
                    for ph in photos.get(p.id, [])
                ],
                "likes": p.likes,
                "comments": p.comments,
                "liked": p.id in liked,
                "mine": viewer is not None and p.author_id == viewer.id,
                "created_at": p.created_at,
            }
        )
    return out


def feed_posts(db: Session, viewer: User, before: datetime | None, limit: int) -> list[Post]:
    """Discover: public posts, my contacts' contacts-only posts, my own, and posts of channels I follow."""
    contacts = contact_ids(db, viewer.id)
    followed = select(ChannelFollow.channel_id).where(ChannelFollow.user_id == viewer.id)
    active_channels = select(Channel.id).where(Channel.status == "active")
    stmt = select(Post).where(
        or_(
            Post.author_id == viewer.id,
            and_(
                Post.channel_id.is_(None),
                Post.status == "visible",
                or_(Post.visibility == "everyone", Post.author_id.in_(contacts) if contacts else false()),
            ),
            and_(Post.channel_id.in_(followed), Post.channel_id.in_(active_channels), Post.status == "visible"),
        ),
        Post.status != "deleted",
    )
    if before is not None:
        stmt = stmt.where(Post.created_at < before)
    return list(db.scalars(stmt.order_by(Post.created_at.desc()).limit(limit)))


def channel_posts(db: Session, viewer: User, channel_id: uuid.UUID, before: datetime | None, limit: int) -> list[Post]:
    channel = _channel(db, channel_id, viewer)
    stmt = select(Post).where(Post.channel_id == channel.id, Post.status != "deleted")
    if not (viewer.role in STAFF_VIEW or is_channel_admin(db, channel, viewer)):
        stmt = stmt.where(Post.status == "visible")
    if before is not None:
        stmt = stmt.where(Post.created_at < before)
    return list(db.scalars(stmt.order_by(Post.created_at.desc()).limit(limit)))


def user_posts(db: Session, viewer: User, author_id: uuid.UUID, limit: int) -> list[Post]:
    contacts = contact_ids(db, author_id)
    rows = db.scalars(
        select(Post)
        .where(Post.author_id == author_id, Post.channel_id.is_(None), Post.status != "deleted")
        .order_by(Post.created_at.desc())
        .limit(limit)
    )
    return [p for p in rows if _can_see_post(db, viewer, p, contacts)]


# ---------- reports and moderation ----------


def report(db: Session, user: User, target_type: str, target_id: uuid.UUID, reason: str, note: str) -> ContentReport:
    owner: uuid.UUID
    if target_type == "post":
        post = get_post(db, user, target_id, lock=True)
        owner = post.author_id
    elif target_type == "comment":
        comment = db.get(PostComment, target_id, with_for_update=True)
        if comment is None or comment.status != "visible":
            raise NotFound("Comment not found")
        get_post(db, user, comment.post_id)
        owner = comment.user_id
    elif target_type == "channel":
        owner = _channel(db, target_id, user).owner_id
    else:
        raise AppError("Report a post, comment or channel", code="target_invalid")
    if owner == user.id:
        raise AppError("You cannot report your own content", code="own_content")
    if db.scalar(
        select(ContentReport.id).where(
            ContentReport.target_type == target_type,
            ContentReport.target_id == target_id,
            ContentReport.reporter_id == user.id,
        )
    ):
        raise Conflict("You have already reported this", code="already_reported")
    item = ContentReport(
        id=uuid.uuid4(),
        target_type=target_type,
        target_id=target_id,
        reporter_id=user.id,
        reason=reason,
        note=note.strip()[:500],
        created_at=clock.now(),
    )
    db.add(item)
    db.flush()
    open_reports = db.scalar(
        select(func.count())
        .select_from(ContentReport)
        .where(
            ContentReport.target_type == target_type,
            ContentReport.target_id == target_id,
            ContentReport.status == "open",
        )
    )
    if (open_reports or 0) >= get_settings().reports_to_auto_hide:
        if target_type == "post":
            hidden = db.get(Post, target_id)
            if hidden is not None and hidden.status == "visible":
                hidden.status = "under_review"
        elif target_type == "comment":
            comment = db.get(PostComment, target_id)
            if comment is not None and comment.status == "visible":
                comment.status = "under_review"
                db.execute(
                    update(Post).where(Post.id == comment.post_id).values(comments=func.greatest(Post.comments - 1, 0))
                )
    return item


def report_queue(db: Session, limit: int) -> list[dict[str, Any]]:
    """Open reports grouped by what was reported, most reported first, with the content to judge."""
    rows = db.execute(
        select(
            ContentReport.target_type,
            ContentReport.target_id,
            func.count(),
            func.min(ContentReport.created_at),
            func.array_agg(ContentReport.reason),
            func.array_agg(ContentReport.note),
        )
        .where(ContentReport.status == "open")
        .group_by(ContentReport.target_type, ContentReport.target_id)
        .order_by(func.count().desc(), func.min(ContentReport.created_at))
        .limit(limit)
    ).all()
    out = []
    for target_type, target_id, count, first, reasons, notes in rows:
        item: dict[str, Any] = {
            "target_type": target_type,
            "target_id": target_id,
            "reports": count,
            "first_at": first,
            "reasons": sorted(set(reasons)),
            "notes": [n for n in notes if n],
        }
        if target_type == "post":
            post = db.get(Post, target_id)
            if post is None:
                continue
            item["content"] = post_views(db, None, [post])[0]
        elif target_type == "comment":
            comment = db.get(PostComment, target_id)
            if comment is None:
                continue
            author = db.get(User, comment.user_id)
            item["content"] = {
                "text": comment.text,
                "status": comment.status,
                "author": _person(author),
                "post_id": comment.post_id,
            }
        else:
            channel = db.get(Channel, target_id)
            if channel is None:
                continue
            owner = db.get(User, channel.owner_id)
            item["content"] = {
                "name": channel.name,
                "handle": channel.handle,
                "description": channel.description,
                "status": channel.status,
                "followers": channel.followers,
                "owner": _person(owner),
            }
        out.append(item)
    return out


def moderate(db: Session, moderator: User, target_type: str, target_id: uuid.UUID, action: str) -> None:
    """'remove' takes it down (a channel is suspended); 'restore' puts it back and dismisses the reports."""
    if action not in ("remove", "restore"):
        raise AppError("Action must be remove or restore", code="invalid_action")
    remove = action == "remove"
    if target_type == "post":
        post = db.get(Post, target_id, with_for_update=True)
        if post is None:
            raise NotFound("Post not found")
        post.status = "removed" if remove else "visible"
    elif target_type == "comment":
        comment = db.get(PostComment, target_id, with_for_update=True)
        if comment is None:
            raise NotFound("Comment not found")
        was_visible = comment.status == "visible"
        comment.status = "removed" if remove else "visible"
        delta = (-1 if was_visible else 0) if remove else (0 if was_visible else 1)
        db.execute(
            update(Post).where(Post.id == comment.post_id).values(comments=func.greatest(Post.comments + delta, 0))
        )
    elif target_type == "channel":
        channel = db.get(Channel, target_id, with_for_update=True)
        if channel is None:
            raise NotFound("Channel not found")
        channel.status = "suspended" if remove else "active"
    else:
        raise AppError("Unknown content", code="target_invalid")
    now = clock.now()
    for item in db.scalars(
        select(ContentReport).where(
            ContentReport.target_type == target_type,
            ContentReport.target_id == target_id,
            ContentReport.status == "open",
        )
    ):
        item.status, item.decided_by, item.decided_at = ("actioned" if remove else "dismissed"), moderator.id, now


def open_report_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(
                select(ContentReport.target_type, ContentReport.target_id)
                .where(ContentReport.status == "open")
                .group_by(ContentReport.target_type, ContentReport.target_id)
                .subquery()
            )
        )
        or 0
    )

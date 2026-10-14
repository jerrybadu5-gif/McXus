"""Marketplace: listings, photos, search, buying from a listing, reviews, seller profiles and reports."""

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app import clock, kyc
from app.config import get_settings
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.escrow import service as escrow
from app.marketplace import media, moderation, trust
from app.models import Category, Listing, ListingPhoto, ListingReport, Location, Order, OrderEvent, Review, User

PUBLIC_STATUSES = ("active", "sold_out")
SELLER_EDITABLE = ("active", "paused", "sold_out")
DELIVERY_OPTIONS = ("meetup", "pickup", "seller_delivers", "courier")
REVIEWABLE = ("RELEASED", "RESOLVED")
STAFF_VIEW = ("moderator", "support", "admin")


# ---------- reference data ----------


def category_tree(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(Category).where(Category.banned.is_(False)).order_by(Category.sort, Category.name))
    parents: dict[int, dict[str, Any]] = {}
    children: list[Category] = []
    for c in rows:
        if c.parent_id is None:
            parents[c.id] = {"id": c.id, "slug": c.slug, "name": c.name, "children": []}
        else:
            children.append(c)
    for c in children:
        parents[c.parent_id]["children"].append({"id": c.id, "slug": c.slug, "name": c.name})  # type: ignore[index]
    return list(parents.values())


def locations(db: Session, parent_id: int | None) -> list[Location]:
    stmt = select(Location).where(
        Location.parent_id.is_(None) if parent_id is None else Location.parent_id == parent_id
    )
    return list(db.scalars(stmt.order_by(Location.level, Location.name)))


def location_names(db: Session, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return dict(db.execute(select(Location.id, Location.name).where(Location.id.in_(wanted))).all())


def _check_location(db: Session, province_id: int, district_id: int | None, suburb_id: int | None) -> None:
    province = db.get(Location, province_id)
    if province is None or province.level != "province":
        raise AppError("Choose a province", code="invalid_location")
    if district_id is not None:
        district = db.get(Location, district_id)
        if district is None or district.level != "district" or district.parent_id != province_id:
            raise AppError("That district is not in the chosen province", code="invalid_location")
    if suburb_id is not None:
        suburb = db.get(Location, suburb_id)
        allowed_parents = {province_id, district_id}
        if suburb is None or suburb.level != "suburb" or suburb.parent_id not in allowed_parents:
            raise AppError("That suburb is not in the chosen area", code="invalid_location")


def _check_category(db: Session, category_id: int) -> None:
    category = db.get(Category, category_id)
    if category is None:
        raise AppError("Choose a category", code="invalid_category")
    if category.banned:
        raise AppError(f"{category.name} cannot be sold on McXus", code="prohibited_content")
    has_children = db.scalar(select(func.count()).select_from(Category).where(Category.parent_id == category_id))
    if has_children:
        raise AppError("Choose a more specific category", code="invalid_category")


def _category_ids(db: Session, slug: str) -> list[int]:
    category = db.scalars(select(Category).where(Category.slug == slug, Category.banned.is_(False))).first()
    if category is None:
        raise NotFound("Category not found")
    child_ids = list(db.scalars(select(Category.id).where(Category.parent_id == category.id)))
    return [category.id, *child_ids]


# ---------- listings ----------


@dataclass
class ListingInput:
    title: str
    description: str
    category_id: int
    price: Decimal
    quantity: int
    condition: str
    delivery_options: list[str]
    province_id: int
    district_id: int | None = None
    suburb_id: int | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    meetup_address: str = ""


@dataclass
class DeliveryPlace:
    """How and where an order changes hands. GPS point first; the address/landmark helps people find it."""

    method: str
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    address: str = ""


def _check_point(latitude: Decimal | None, longitude: Decimal | None, address: str) -> None:
    if (latitude is None) != (longitude is None):
        raise AppError("Send both latitude and longitude, or neither", code="invalid_location")
    if address:
        moderation.check_listing_text("", address)


def create_listing(db: Session, seller: User, data: ListingInput) -> Listing:
    kyc.require(seller.kyc_tier, "sell")
    _validate(db, data)
    listing = Listing(
        id=uuid.uuid4(),
        seller_id=seller.id,
        title=data.title.strip(),
        description=data.description.strip(),
        category_id=data.category_id,
        price=data.price,
        quantity_available=data.quantity,
        condition=data.condition,
        delivery_options=data.delivery_options,
        province_id=data.province_id,
        district_id=data.district_id,
        suburb_id=data.suburb_id,
        latitude=data.latitude,
        longitude=data.longitude,
        meetup_address=data.meetup_address.strip(),
        status="active",
    )
    db.add(listing)
    db.flush()
    return listing


def _validate(db: Session, data: ListingInput) -> None:
    moderation.check_listing_text(data.title, data.description)
    _check_category(db, data.category_id)
    _check_location(db, data.province_id, data.district_id, data.suburb_id)
    bad = set(data.delivery_options) - set(DELIVERY_OPTIONS)
    if bad or not data.delivery_options:
        raise AppError(f"Delivery options must be from {', '.join(DELIVERY_OPTIONS)}", code="invalid_delivery")
    _check_point(data.latitude, data.longitude, data.meetup_address)


def get_listing(db: Session, listing_id: uuid.UUID, viewer: User | None = None, *, lock: bool = False) -> Listing:
    stmt = select(Listing).where(Listing.id == listing_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    listing = db.scalars(stmt).first()
    visible = listing is not None and (
        listing.status in PUBLIC_STATUSES
        or (viewer is not None and (viewer.id == listing.seller_id or viewer.role in STAFF_VIEW))
    )
    if not visible:
        raise NotFound("Listing not found")
    assert listing is not None
    return listing


def _own_listing(db: Session, seller: User, listing_id: uuid.UUID) -> Listing:
    listing = get_listing(db, listing_id, seller, lock=True)
    if listing.seller_id != seller.id:
        raise Forbidden("Only the seller can change this listing")
    if listing.status not in SELLER_EDITABLE:
        raise Conflict(
            f"This listing is {listing.status.replace('_', ' ')} and cannot be changed", code="listing_locked"
        )
    return listing


def update_listing(db: Session, seller: User, listing_id: uuid.UUID, data: ListingInput) -> Listing:
    listing = _own_listing(db, seller, listing_id)
    _validate(db, data)
    listing.title, listing.description = data.title.strip(), data.description.strip()
    listing.category_id, listing.price, listing.condition = data.category_id, data.price, data.condition
    listing.delivery_options = data.delivery_options
    listing.province_id, listing.district_id, listing.suburb_id = data.province_id, data.district_id, data.suburb_id
    listing.latitude, listing.longitude = data.latitude, data.longitude
    listing.meetup_address = data.meetup_address.strip()
    listing.quantity_available = data.quantity
    if data.quantity == 0 and listing.status == "active":
        listing.status = "sold_out"
    elif data.quantity > 0 and listing.status == "sold_out":
        listing.status = "active"
    return listing


def set_listing_status(db: Session, seller: User, listing_id: uuid.UUID, status: str) -> Listing:
    """Seller can pause, re-activate or close (stop selling for good) a listing."""
    listing = _own_listing(db, seller, listing_id)
    if status == "active":
        listing.status = "active" if listing.quantity_available > 0 else "sold_out"
    elif status in ("paused", "closed"):
        listing.status = status
    else:
        raise AppError("Status must be active, paused or closed", code="invalid_status")
    return listing


# ---------- photos ----------


def add_photo(db: Session, seller: User, listing_id: uuid.UUID, data: bytes) -> ListingPhoto:
    listing = _own_listing(db, seller, listing_id)
    existing = db.scalar(select(func.count()).select_from(ListingPhoto).where(ListingPhoto.listing_id == listing.id))
    limit = get_settings().max_photos_per_listing
    if existing is not None and existing >= limit:
        raise Conflict(f"A listing can have up to {limit} photos", code="too_many_photos")
    processed = media.process(data)
    photo_id = uuid.uuid4()
    key = f"listings/{listing.id}/{photo_id}"
    store = media.storage()
    store.save(f"{key}.jpg", processed.full)
    store.save(f"{key}_t.jpg", processed.thumb)
    photo = ListingPhoto(
        id=photo_id,
        listing_id=listing.id,
        position=existing or 0,
        key=key,
        width=processed.width,
        height=processed.height,
        bytes=len(processed.full),
    )
    db.add(photo)
    db.flush()
    return photo


def delete_photo(db: Session, seller: User, listing_id: uuid.UUID, photo_id: uuid.UUID) -> None:
    listing = _own_listing(db, seller, listing_id)
    photo = db.scalars(
        select(ListingPhoto).where(ListingPhoto.id == photo_id, ListingPhoto.listing_id == listing.id)
    ).first()
    if photo is None:
        raise NotFound("Photo not found")
    db.delete(photo)
    store = media.storage()
    store.delete(f"{photo.key}.jpg")
    store.delete(f"{photo.key}_t.jpg")


def photos_for(db: Session, listing_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ListingPhoto]]:
    result: dict[uuid.UUID, list[ListingPhoto]] = {lid: [] for lid in listing_ids}
    if listing_ids:
        stmt = select(ListingPhoto).where(ListingPhoto.listing_id.in_(listing_ids))
        for photo in db.scalars(stmt.order_by(ListingPhoto.position, ListingPhoto.created_at)):
            result[photo.listing_id].append(photo)
    return result


# ---------- search ----------

SORTS: dict[str, list[Any]] = {
    "newest": [Listing.created_at.desc()],
    "price_low": [Listing.price.asc(), Listing.created_at.desc()],
    "price_high": [Listing.price.desc(), Listing.created_at.desc()],
}


def _prefix_query(q: str) -> str | None:
    """'solar gen' -> 'solar:* & gen:*' so partly typed words match (handy on a phone)."""
    tokens = re.findall(r"[0-9a-zA-Z]+", q.lower())[:8]
    return " & ".join(f"{t}:*" for t in tokens) or None


@dataclass
class SearchFilters:
    q: str = ""
    category: str | None = None
    province_id: int | None = None
    district_id: int | None = None
    suburb_id: int | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    condition: str | None = None
    seller_id: uuid.UUID | None = None
    sort: str = "newest"
    limit: int = 20
    offset: int = 0


def search(db: Session, f: SearchFilters) -> list[Listing]:
    stmt = select(Listing).where(Listing.status == "active")
    order_by = SORTS.get(f.sort, SORTS["newest"])
    tsquery = _prefix_query(f.q) if f.q else None
    if tsquery:
        query = func.to_tsquery("simple", tsquery)
        tsv: Any = literal_column("listings.search_tsv")
        stmt = stmt.where(tsv.op("@@")(query))
        if f.sort == "relevance":
            order_by = [func.ts_rank(tsv, query).desc(), Listing.created_at.desc()]
    if f.category:
        stmt = stmt.where(Listing.category_id.in_(_category_ids(db, f.category)))
    for column, value in (
        (Listing.province_id, f.province_id),
        (Listing.district_id, f.district_id),
        (Listing.suburb_id, f.suburb_id),
        (Listing.condition, f.condition),
        (Listing.seller_id, f.seller_id),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    if f.min_price is not None:
        stmt = stmt.where(Listing.price >= f.min_price)
    if f.max_price is not None:
        stmt = stmt.where(Listing.price <= f.max_price)
    return list(db.scalars(stmt.order_by(*order_by).limit(f.limit).offset(f.offset)))


# ---------- buying ----------


DELIVERED_TO_BUYER = ("seller_delivers", "courier")


def buy(db: Session, buyer: User, listing_id: uuid.UUID, quantity: int, delivery: DeliveryPlace | None = None) -> Order:
    """Create an order from a listing. Stock is taken when the buyer pays (first to pay wins).

    Delivery: for meet-up/pickup the seller's meet-up point is used unless the buyer proposes another; for
    seller delivery/courier the buyer must give a GPS point or an address."""
    listing = get_listing(db, listing_id, buyer)
    if listing.status != "active":
        raise Conflict("This item is no longer available", code="sold_out")
    if quantity < 1 or quantity > listing.quantity_available:
        raise Conflict(f"Only {listing.quantity_available} available", code="not_enough_stock")
    place = delivery or DeliveryPlace(method=listing.delivery_options[0] if listing.delivery_options else "meetup")
    if place.method not in listing.delivery_options:
        raise AppError("The seller does not offer that delivery option", code="delivery_not_offered")
    _check_point(place.latitude, place.longitude, place.address)
    has_point = place.latitude is not None or bool(place.address.strip())
    if place.method in DELIVERED_TO_BUYER and not has_point:
        raise AppError(
            "Give your delivery location (use your GPS or type an address)", code="delivery_location_required"
        )
    if place.method not in DELIVERED_TO_BUYER and not has_point:
        place = DeliveryPlace(place.method, listing.latitude, listing.longitude, listing.meetup_address)
    order = escrow.create_order(
        db,
        buyer,
        listing.seller_id,
        listing.title,
        listing.price * quantity,
        listing_id=listing.id,
        quantity=quantity,
    )
    order.delivery_method = place.method
    order.delivery_latitude, order.delivery_longitude = place.latitude, place.longitude
    order.delivery_address = place.address.strip()
    return order


def set_delivery_place(
    db: Session, user: User, order_id: uuid.UUID, latitude: Decimal | None, longitude: Decimal | None, address: str
) -> Order:
    """Buyer or seller moves the handover point (e.g. "meet at the BSP ATM instead") while the order is open."""
    order = escrow.get_order(db, order_id, lock=True)
    if user.id not in (order.buyer_id, order.seller_id):
        raise NotFound("Order not found")
    if order.closed_at is not None:
        raise Conflict("This order is closed", code="order_closed")
    _check_point(latitude, longitude, address)
    if latitude is None and not address.strip():
        raise AppError("Give a GPS point or an address", code="delivery_location_required")
    order.delivery_latitude, order.delivery_longitude = latitude, longitude
    order.delivery_address = address.strip()
    db.add(
        OrderEvent(
            order_id=order.id,
            from_status=order.status,
            to_status=order.status,
            actor_id=user.id,
            reason="delivery location changed",
            data={},
            created_at=clock.now(),
        )
    )
    return order


# ---------- reviews and sellers ----------


def review(db: Session, buyer: User, order_id: uuid.UUID, stars: int, comment: str) -> Review:
    order = escrow.get_order(db, order_id)
    if order.buyer_id != buyer.id:
        raise Forbidden("Only the buyer can rate this order")
    if order.status not in REVIEWABLE:
        raise Conflict("You can rate the seller once the order is completed", code="not_completed")
    if db.scalar(select(Review.id).where(Review.order_id == order.id)):
        raise Conflict("You have already rated this order", code="already_reviewed")
    moderation.check_listing_text("", comment)
    item = Review(
        id=uuid.uuid4(),
        order_id=order.id,
        seller_id=order.seller_id,
        buyer_id=buyer.id,
        stars=stars,
        comment=comment.strip(),
        created_at=clock.now(),
    )
    db.add(item)
    db.flush()
    return item


def seller_profile(db: Session, seller_id: uuid.UUID) -> dict[str, Any]:
    seller = db.get(User, seller_id)
    if seller is None or seller.status != "active":
        raise NotFound("Seller not found")
    t = trust.for_seller(db, seller.id)
    active = db.scalar(
        select(func.count()).select_from(Listing).where(Listing.seller_id == seller.id, Listing.status == "active")
    )
    return {
        "id": seller.id,
        "name": seller.store_name or seller.display_name or "McXus seller",
        "is_store": bool(seller.store_name),
        "verified_business": seller.kyc_tier >= 3,
        "bio": seller.bio,
        "badge": t.badge,
        "rating": t.rating,
        "reviews": t.reviews,
        "completed_sales": t.completed_sales,
        "active_listings": active or 0,
        "member_since": seller.created_at,
    }


def recent_reviews(db: Session, seller_id: uuid.UUID, limit: int, offset: int) -> list[Review]:
    stmt = select(Review).where(Review.seller_id == seller_id).order_by(Review.created_at.desc())
    return list(db.scalars(stmt.limit(limit).offset(offset)))


# ---------- reports and moderation ----------


def report(db: Session, user: User, listing_id: uuid.UUID, reason: str, note: str) -> ListingReport:
    listing = get_listing(db, listing_id, user, lock=True)
    if listing.seller_id == user.id:
        raise AppError("You cannot report your own listing", code="own_listing")
    if db.scalar(
        select(ListingReport.id).where(ListingReport.listing_id == listing.id, ListingReport.reporter_id == user.id)
    ):
        raise Conflict("You have already reported this listing", code="already_reported")
    item = ListingReport(id=uuid.uuid4(), listing_id=listing.id, reporter_id=user.id, reason=reason, note=note)
    db.add(item)
    db.flush()
    open_reports = db.scalar(
        select(func.count())
        .select_from(ListingReport)
        .where(ListingReport.listing_id == listing.id, ListingReport.status == "open")
    )
    if (open_reports or 0) >= get_settings().reports_to_auto_hide and listing.status in PUBLIC_STATUSES:
        listing.status = "under_review"
    return item


def open_reports(db: Session, limit: int, offset: int) -> list[ListingReport]:
    stmt = select(ListingReport).where(ListingReport.status == "open").order_by(ListingReport.created_at)
    return list(db.scalars(stmt.limit(limit).offset(offset)))


def moderate(db: Session, moderator: User, listing_id: uuid.UUID, action: str) -> Listing:
    """'remove' takes the listing down; 'restore' puts it back and dismisses the reports."""
    listing = get_listing(db, listing_id, moderator, lock=True)
    if action == "remove":
        listing.status, report_status = "removed", "actioned"
    elif action == "restore":
        listing.status = "active" if listing.quantity_available > 0 else "sold_out"
        report_status = "dismissed"
    else:
        raise AppError("Action must be remove or restore", code="invalid_action")
    now = clock.now()
    for item in db.scalars(
        select(ListingReport).where(ListingReport.listing_id == listing.id, ListingReport.status == "open")
    ):
        item.status, item.decided_by, item.decided_at = report_status, moderator.id, now
    return listing


def seller_cards(db: Session, seller_ids: set[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """Name and badge for each seller in a result list (batched)."""
    if not seller_ids:
        return {}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(seller_ids)))}
    trusts = trust.for_sellers(db, seller_ids)
    return {
        sid: {
            "id": sid,
            "name": users[sid].store_name or users[sid].display_name or "McXus seller",
            "badge": trusts[sid].badge,
            "rating": trusts[sid].rating,
            "reviews": trusts[sid].reviews,
        }
        for sid in seller_ids
        if sid in users
    }

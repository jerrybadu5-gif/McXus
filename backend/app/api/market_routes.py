"""Marketplace HTTP API (module M2). Browsing is public; selling, buying and reporting need sign-in."""

import uuid
from dataclasses import asdict
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.market_schemas import (
    BuyIn,
    CategoryOut,
    Condition,
    ListingIn,
    ListingOut,
    LocationOut,
    ModerationIn,
    PhotoOut,
    ProfileIn,
    ReportIn,
    ReportOut,
    ReviewIn,
    ReviewOut,
    SellerCard,
    SellerOut,
    StatusIn,
    TrustOut,
)
from app.api.schemas import OrderOut, UserOut
from app.auth.deps import current_user, optional_user, require_role
from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.idempotency import run_once
from app.marketplace import media, trust
from app.marketplace import service as market
from app.models import Listing, User

router = APIRouter(prefix="/v1")
DB = Annotated[Session, Depends(get_db)]
Me = Annotated[User, Depends(current_user)]
MaybeMe = Annotated[User | None, Depends(optional_user)]
Moderator = Annotated[User, Depends(require_role("moderator"))]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]
Page = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _to_input(body: ListingIn) -> market.ListingInput:
    return market.ListingInput(**body.model_dump())


def listing_cards(db: Session, listings: list[Listing]) -> list[ListingOut]:
    """Build responses for many listings with a fixed number of queries (photos, places, sellers)."""
    photos = market.photos_for(db, [x.id for x in listings])
    names = market.location_names(db, {i for x in listings for i in (x.province_id, x.district_id, x.suburb_id)})
    sellers = market.seller_cards(db, {x.seller_id for x in listings})
    return [
        ListingOut(
            id=x.id,
            title=x.title,
            description=x.description,
            category_id=x.category_id,
            price=x.price,
            stars_price=x.price,
            quantity_available=x.quantity_available,
            condition=x.condition,
            delivery_options=x.delivery_options,
            province=names.get(x.province_id, ""),
            district=names.get(x.district_id) if x.district_id else None,
            suburb=names.get(x.suburb_id) if x.suburb_id else None,
            location_ids={"province": x.province_id, "district": x.district_id, "suburb": x.suburb_id},
            status=x.status,
            photos=[
                PhotoOut(
                    id=p.id,
                    url=media.url(f"{p.key}.jpg"),
                    thumb_url=media.url(f"{p.key}_t.jpg"),
                    width=p.width,
                    height=p.height,
                )
                for p in photos[x.id]
            ],
            seller=SellerCard(**sellers[x.seller_id]),
            created_at=x.created_at,
        )
        for x in listings
    ]


def _one(db: Session, listing: Listing) -> ListingOut:
    return listing_cards(db, [listing])[0]


# ---------- reference data ----------


@router.get("/categories", tags=["marketplace"])
def categories(db: DB) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in market.category_tree(db)]


@router.get("/locations", tags=["marketplace"])
def locations(db: DB, parent_id: int | None = None) -> list[LocationOut]:
    """No parent: the 22 provinces. With a province id: its districts (and suburbs for NCD).
    With a district id: its suburbs (e.g. Lae)."""
    return [LocationOut.model_validate(x) for x in market.locations(db, parent_id)]


# ---------- listings ----------


@router.get("/listings", tags=["marketplace"])
def search_listings(
    db: DB,
    q: Annotated[str, Query(max_length=100)] = "",
    category: str | None = None,
    province_id: int | None = None,
    district_id: int | None = None,
    suburb_id: int | None = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    condition: Condition | None = None,
    seller_id: uuid.UUID | None = None,
    sort: Annotated[str, Query(pattern="^(newest|price_low|price_high|relevance)$")] = "newest",
    limit: Page = 20,
    offset: Offset = 0,
) -> list[ListingOut]:
    filters = market.SearchFilters(
        q=q,
        category=category,
        province_id=province_id,
        district_id=district_id,
        suburb_id=suburb_id,
        min_price=min_price,
        max_price=max_price,
        condition=condition,
        seller_id=seller_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return listing_cards(db, market.search(db, filters))


@router.post("/listings", status_code=201, tags=["marketplace"])
def create_listing(body: ListingIn, user: Me, db: DB) -> ListingOut:
    listing = market.create_listing(db, user, _to_input(body))
    db.commit()
    return _one(db, listing)


@router.get("/listings/{listing_id}", tags=["marketplace"])
def get_listing(listing_id: uuid.UUID, db: DB, user: MaybeMe) -> ListingOut:
    return _one(db, market.get_listing(db, listing_id, user))


@router.put("/listings/{listing_id}", tags=["marketplace"])
def update_listing(listing_id: uuid.UUID, body: ListingIn, user: Me, db: DB) -> ListingOut:
    listing = market.update_listing(db, user, listing_id, _to_input(body))
    db.commit()
    return _one(db, listing)


@router.post("/listings/{listing_id}/status", tags=["marketplace"])
def set_status(listing_id: uuid.UUID, body: StatusIn, user: Me, db: DB) -> ListingOut:
    listing = market.set_listing_status(db, user, listing_id, body.status)
    db.commit()
    return _one(db, listing)


@router.post("/listings/{listing_id}/photos", status_code=201, tags=["marketplace"])
async def upload_photo(listing_id: uuid.UUID, file: UploadFile, user: Me, db: DB) -> PhotoOut:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError(f"Photos must be under {get_settings().max_upload_mb} MB", code="photo_too_large")
    photo = market.add_photo(db, user, listing_id, data)
    db.commit()
    return PhotoOut(
        id=photo.id,
        url=media.url(f"{photo.key}.jpg"),
        thumb_url=media.url(f"{photo.key}_t.jpg"),
        width=photo.width,
        height=photo.height,
    )


@router.delete("/listings/{listing_id}/photos/{photo_id}", status_code=204, tags=["marketplace"])
def delete_photo(listing_id: uuid.UUID, photo_id: uuid.UUID, user: Me, db: DB) -> None:
    market.delete_photo(db, user, listing_id, photo_id)
    db.commit()


@router.get("/me/listings", tags=["marketplace"])
def my_listings(user: Me, db: DB, limit: Page = 50, offset: Offset = 0) -> list[ListingOut]:
    rows = db.scalars(
        select(Listing)
        .where(Listing.seller_id == user.id)
        .order_by(Listing.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return listing_cards(db, list(rows))


@router.post("/listings/{listing_id}/buy", status_code=201, tags=["marketplace"])
def buy(listing_id: uuid.UUID, body: BuyIn, user: Me, db: DB, key: IdemKey = None) -> OrderOut:
    """Start an order from a listing. Then pay with POST /v1/orders/{id}/pay — the first buyer to pay gets it."""
    result = run_once(
        db,
        user.id,
        key,
        {"op": "buy", "listing": listing_id, **body.model_dump()},
        lambda: OrderOut.model_validate(market.buy(db, user, listing_id, body.quantity)),
    )
    return OrderOut.model_validate(result)


@router.post("/listings/{listing_id}/report", status_code=201, tags=["marketplace"])
def report(listing_id: uuid.UUID, body: ReportIn, user: Me, db: DB) -> ReportOut:
    item = market.report(db, user, listing_id, body.reason, body.note)
    db.commit()
    return ReportOut.model_validate(item)


# ---------- reviews, sellers, profile ----------


@router.post("/orders/{order_id}/review", status_code=201, tags=["marketplace"])
def review(order_id: uuid.UUID, body: ReviewIn, user: Me, db: DB) -> ReviewOut:
    item = market.review(db, user, order_id, body.stars, body.comment)
    db.commit()
    return ReviewOut.model_validate(item)


@router.get("/sellers/{seller_id}", tags=["marketplace"])
def seller(seller_id: uuid.UUID, db: DB) -> SellerOut:
    return SellerOut.model_validate(market.seller_profile(db, seller_id))


@router.get("/sellers/{seller_id}/reviews", tags=["marketplace"])
def seller_reviews(seller_id: uuid.UUID, db: DB, limit: Page = 20, offset: Offset = 0) -> list[ReviewOut]:
    return [ReviewOut.model_validate(r) for r in market.recent_reviews(db, seller_id, limit, offset)]


@router.put("/me/profile", tags=["marketplace"])
def update_profile(body: ProfileIn, user: Me, db: DB) -> UserOut:
    user.display_name = body.display_name.strip()
    user.store_name = body.store_name.strip() if body.store_name else None
    user.bio = body.bio.strip()
    db.commit()
    return UserOut.model_validate(user)


# ---------- moderators ----------


@router.get("/mod/reports", tags=["moderation"])
def reports_queue(staff: Moderator, db: DB, limit: Page = 50, offset: Offset = 0) -> list[ReportOut]:
    return [ReportOut.model_validate(r) for r in market.open_reports(db, limit, offset)]


@router.post("/mod/listings/{listing_id}/decision", tags=["moderation"])
def moderate(listing_id: uuid.UUID, body: ModerationIn, staff: Moderator, db: DB) -> ListingOut:
    listing = market.moderate(db, staff, listing_id, body.action)
    db.commit()
    return _one(db, listing)


@router.get("/mod/sellers/{seller_id}/trust", tags=["moderation"])
def seller_trust(seller_id: uuid.UUID, staff: Moderator, db: DB) -> TrustOut:
    """Raw trust score and its inputs (staff only; the public sees the badge)."""
    return TrustOut(**asdict(trust.for_seller(db, seller_id)))

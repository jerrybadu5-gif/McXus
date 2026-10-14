"""Marketplace request and response bodies."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Price = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2, description="PGK, e.g. 150.00")]
Delivery = Literal["meetup", "pickup", "seller_delivers", "courier"]
# PNG and its islands lie between about 0-12°S and 140-160°E; 5 decimals ≈ 1 m.
Latitude = Annotated[Decimal, Field(ge=-12, le=0, decimal_places=5)]
Longitude = Annotated[Decimal, Field(ge=140, le=160, decimal_places=5)]


class PlaceOut(BaseModel):
    latitude: Decimal | None
    longitude: Decimal | None
    address: str


class DeliveryIn(BaseModel):
    method: Delivery
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    address: str = Field(default="", max_length=200, examples=["Blue house behind Eriku church"])


class DeliveryPlaceIn(BaseModel):
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    address: str = Field(default="", max_length=200)


Condition = Literal["new", "like_new", "good", "fair", "not_applicable"]


class CategoryOut(BaseModel):
    id: int
    slug: str
    name: str
    children: list["CategoryOut"] = []


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    level: str
    name: str
    parent_id: int | None
    region: str


class ListingIn(BaseModel):
    title: str = Field(min_length=3, max_length=140, examples=["Solar lamp, 2 bulbs + phone charger"])
    description: str = Field(default="", max_length=4000)
    category_id: int
    price: Price
    quantity: int = Field(default=1, ge=0, le=10000)
    condition: Condition = "good"
    delivery_options: list[Delivery] = Field(default=["meetup"], min_length=1)
    province_id: int
    district_id: int | None = None
    suburb_id: int | None = None
    latitude: Latitude | None = Field(default=None, description="Meet-up / pickup point (a public place, not home)")
    longitude: Longitude | None = None
    meetup_address: str = Field(default="", max_length=200, examples=["Eriku market gate, Lae"])


class StatusIn(BaseModel):
    status: Literal["active", "paused", "closed"]


class PhotoOut(BaseModel):
    id: uuid.UUID
    url: str
    thumb_url: str
    width: int
    height: int


class SellerCard(BaseModel):
    id: uuid.UUID
    name: str
    badge: str
    rating: Decimal | None
    reviews: int


class ListingOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    category_id: int
    price: Decimal
    stars_price: Decimal = Field(description="Same value in Stars (1 Star = K1)")
    quantity_available: int
    condition: str
    delivery_options: list[str]
    province: str
    district: str | None
    suburb: str | None
    location_ids: dict[str, int | None]
    meetup: PlaceOut | None = Field(description="Seller's meet-up / pickup point: GPS first, address second")
    status: str
    photos: list[PhotoOut]
    seller: SellerCard
    created_at: datetime


class BuyIn(BaseModel):
    quantity: int = Field(default=1, ge=1, le=10000)
    delivery: DeliveryIn | None = Field(
        default=None, description="Omit to use the seller's first option and meet-up point"
    )


class ReportIn(BaseModel):
    reason: Literal["prohibited", "scam", "wrong_category", "offensive", "other"]
    note: str = Field(default="", max_length=500)


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    listing_id: uuid.UUID
    reporter_id: uuid.UUID
    reason: str
    note: str
    status: str
    created_at: datetime


class ReviewIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    order_id: uuid.UUID
    stars: int
    comment: str
    created_at: datetime


class SellerOut(BaseModel):
    id: uuid.UUID
    name: str
    is_store: bool
    verified_business: bool
    bio: str
    badge: str
    rating: Decimal | None
    reviews: int
    completed_sales: int
    active_listings: int
    member_since: datetime


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    store_name: str | None = Field(default=None, min_length=2, max_length=80)
    bio: str = Field(default="", max_length=500)


class ModerationIn(BaseModel):
    action: Literal["remove", "restore"]


class TrustOut(BaseModel):
    score: int
    badge: str
    rating: Decimal | None
    reviews: int
    completed_sales: int
    disputes_lost: int
    late_cancellations: int

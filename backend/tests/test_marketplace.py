"""Marketplace (M2): listings, search, first-to-pay stock reservation, photos, reviews, trust, reports."""

import io
import os
from decimal import Decimal as D

import pytest
from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.errors import AppError, Conflict, Forbidden
from app.escrow import service as escrow
from app.ledger.service import integrity_report, user_account
from app.marketplace import service as market
from app.marketplace import trust
from app.models import Category, Listing, Location
from tests.conftest import auth, make_user


def loc(db, name, level):
    return db.scalars(select(Location).where(Location.name == name, Location.level == level)).one().id


def cat(db, slug):
    return db.scalars(select(Category).where(Category.slug == slug)).one().id


def listing_input(db, **overrides):
    data = dict(
        title="Solar lamp with phone charger",
        description="Two bulbs, 10W panel. Pickup at Eriku.",
        category_id=cat(db, "tv-audio"),
        price=D("120.00"),
        quantity=1,
        condition="new",
        delivery_options=["meetup", "pickup"],
        province_id=loc(db, "Morobe", "province"),
        district_id=loc(db, "Lae", "district"),
        suburb_id=loc(db, "Eriku", "suburb"),
    )
    data.update(overrides)
    return market.ListingInput(**data)


def new_listing(db, seller, **overrides):
    listing = market.create_listing(db, seller, listing_input(db, **overrides))
    db.commit()
    return listing


def wallet(db, user):
    db.expire_all()
    return user_account(db, user.id, "wallet").balance


def listing_now(db, listing_id):
    db.expire_all()
    return db.get(Listing, listing_id)


# ---------- reference data ----------


def test_locations_seeded(db):
    provinces = market.locations(db, None)
    assert len(provinces) == 22
    ncd = next(p for p in provinces if p.name == "National Capital District")
    children = market.locations(db, ncd.id)
    assert {"Moresby South", "Gerehu", "Waigani"} <= {c.name for c in children}
    lae_suburbs = market.locations(db, loc(db, "Lae", "district"))
    assert "Eriku" in {s.name for s in lae_suburbs}


def test_category_tree_hides_banned(db):
    tree = market.category_tree(db)
    slugs = {c["slug"] for c in tree} | {k["slug"] for c in tree for k in c["children"]}
    assert "phones-tablets" in slugs and "firearms" not in slugs and "betel-nut" not in slugs


# ---------- creating listings ----------


def test_create_listing(db, users):
    listing = new_listing(db, users["seller"])
    assert listing.status == "active" and listing.quantity_available == 1


@pytest.mark.parametrize("title", ["Pump action shotgun", "Fresh buai for sale", "Cold beer carton", "Spak brus"])
def test_prohibited_words_blocked(db, users, title):
    with pytest.raises(AppError, match="cannot include"):
        market.create_listing(db, users["seller"], listing_input(db, title=title))


@pytest.mark.parametrize("title", ["Glue gun for crafts", "Weed killer 1L", "Printer cartridges HP 65"])
def test_innocent_words_allowed(db, users, title):
    market.create_listing(db, users["seller"], listing_input(db, title=title))


def test_banned_and_parent_categories_refused(db, users):
    with pytest.raises(AppError, match="cannot be sold"):
        market.create_listing(db, users["seller"], listing_input(db, category_id=cat(db, "alcohol")))
    with pytest.raises(AppError, match="more specific"):
        market.create_listing(db, users["seller"], listing_input(db, category_id=cat(db, "electronics")))


def test_location_must_be_consistent(db, users):
    with pytest.raises(AppError, match="not in the chosen province"):
        market.create_listing(db, users["seller"], listing_input(db, province_id=loc(db, "Enga", "province")))
    with pytest.raises(AppError, match="not in the chosen area"):
        market.create_listing(db, users["seller"], listing_input(db, suburb_id=loc(db, "Gerehu", "suburb")))


def test_ncd_suburb_without_district(db, users):
    new_listing(
        db,
        users["seller"],
        province_id=loc(db, "National Capital District", "province"),
        district_id=None,
        suburb_id=loc(db, "Gerehu", "suburb"),
    )


def test_basic_tier_cannot_sell(db):
    basic = make_user(db, tier=1)
    with pytest.raises(Forbidden, match="level 2"):
        market.create_listing(db, basic, listing_input(db))


# ---------- search ----------


def test_search(db, users):
    seller = users["seller"]
    lamp = new_listing(db, seller)
    phone = new_listing(db, seller, title="Samsung A15 phone", category_id=cat(db, "phones-tablets"), price=D("450.00"))
    pom = new_listing(
        db,
        seller,
        title="Office chair",
        category_id=cat(db, "furniture"),
        price=D("80.00"),
        province_id=loc(db, "National Capital District", "province"),
        district_id=None,
        suburb_id=None,
    )
    paused = new_listing(db, seller, title="Solar panel 100W")
    market.set_listing_status(db, seller, paused.id, "paused")
    db.commit()

    def ids(**kw):
        return [x.id for x in market.search(db, market.SearchFilters(**kw))]

    assert ids(q="sol") == [lamp.id]  # prefix match; paused listing hidden
    assert ids(q="samsung phone") == [phone.id]
    assert set(ids(category="electronics")) == {lamp.id, phone.id}  # parent includes children
    assert ids(province_id=loc(db, "National Capital District", "province")) == [pom.id]
    assert set(ids(min_price=D("100"), max_price=D("200"))) == {lamp.id}
    assert ids(sort="price_low") == [pom.id, lamp.id, phone.id]
    assert ids(q="!!! ' ;--") == ids()  # junk query is ignored, not an error


# ---------- first buyer who pays gets the item ----------


def test_first_buyer_to_pay_wins_and_rejection_returns_stock(db, users):
    seller, buyer_a = users["seller"], users["buyer"]
    buyer_b = make_user(db, stars=500)
    listing = new_listing(db, seller)  # quantity 1
    order_a = market.buy(db, buyer_a, listing.id, 1)
    order_b = market.buy(db, buyer_b, listing.id, 1)  # both may start an order
    db.commit()
    escrow.pay(db, buyer_a, order_a.id)
    db.commit()
    assert listing_now(db, listing.id).status == "sold_out"
    with pytest.raises(Conflict, match="someone else has just bought"):
        escrow.pay(db, buyer_b, order_b.id)
    db.rollback()
    assert wallet(db, buyer_b) == D("500.00")  # B was not charged
    assert escrow.get_order(db, order_b.id).status == "CREATED"
    # seller rejects A within 20 minutes -> stock back, B can now pay
    escrow.reject(db, seller, order_a.id, "")
    db.commit()
    assert (listing_now(db, listing.id).status, listing_now(db, listing.id).quantity_available) == ("active", 1)
    escrow.pay(db, buyer_b, order_b.id)
    db.commit()
    assert listing_now(db, listing.id).status == "sold_out"
    assert integrity_report(db)["ok"]


def test_quantity_and_buyer_cancel_restock(db, users):
    listing = new_listing(db, users["seller"], quantity=3)
    order = market.buy(db, users["buyer"], listing.id, 2)
    assert order.amount == D("240.00") and order.quantity == 2
    escrow.pay(db, users["buyer"], order.id)
    db.commit()
    assert listing_now(db, listing.id).quantity_available == 1
    with pytest.raises(Conflict, match="Only 1 available"):
        market.buy(db, users["buyer"], listing.id, 2)
    escrow.cancel(db, users["buyer"], order.id, "")
    db.commit()
    assert listing_now(db, listing.id).quantity_available == 3


def test_released_and_disputed_orders_keep_stock_taken(db, users):
    listing = new_listing(db, users["seller"], quantity=2)
    o1 = market.buy(db, users["buyer"], listing.id, 1)
    _, pin = escrow.pay(db, users["buyer"], o1.id)
    escrow.accept(db, users["seller"], o1.id)
    escrow.handover(db, users["seller"], o1.id, pin)
    o2 = market.buy(db, users["buyer"], listing.id, 1)
    escrow.pay(db, users["buyer"], o2.id)
    escrow.accept(db, users["seller"], o2.id)
    escrow.open_dispute(db, users["buyer"], o2.id, "Not as described")
    escrow.resolve_dispute(db, users["mediator"], o2.id, D("120.00"), "Full refund")
    db.commit()
    assert listing_now(db, listing.id).quantity_available == 0


def test_seller_edits_stock(db, users):
    listing = new_listing(db, users["seller"])
    market.update_listing(db, users["seller"], listing.id, listing_input(db, quantity=0))
    db.commit()
    assert listing_now(db, listing.id).status == "sold_out"
    market.update_listing(db, users["seller"], listing.id, listing_input(db, quantity=4, price=D("99.00")))
    db.commit()
    assert (listing_now(db, listing.id).status, listing_now(db, listing.id).price) == ("active", D("99.00"))
    with pytest.raises(Forbidden):
        market.update_listing(db, users["buyer"], listing.id, listing_input(db))


# ---------- reviews and trust ----------


def complete_sale(db, users, listing, stars=None):
    order = market.buy(db, users["buyer"], listing.id, 1)
    _, pin = escrow.pay(db, users["buyer"], order.id)
    escrow.accept(db, users["seller"], order.id)
    escrow.handover(db, users["seller"], order.id, pin)
    if stars:
        market.review(db, users["buyer"], order.id, stars, "Good seller")
    db.commit()
    return order


def test_reviews_rules(db, users):
    listing = new_listing(db, users["seller"], quantity=5, price=D("20.00"))
    order = market.buy(db, users["buyer"], listing.id, 1)
    escrow.pay(db, users["buyer"], order.id)
    with pytest.raises(Conflict, match="once the order is completed"):
        market.review(db, users["buyer"], order.id, 5, "")
    db.rollback()
    done = complete_sale(db, users, listing)
    with pytest.raises(Forbidden):
        market.review(db, users["seller"], done.id, 5, "")
    market.review(db, users["buyer"], done.id, 4, "Fast handover at Eriku")
    with pytest.raises(Conflict, match="already rated"):
        market.review(db, users["buyer"], done.id, 5, "")


def test_trust_badges(db, users):
    listing = new_listing(db, users["seller"], quantity=10, price=D("20.00"))
    assert trust.for_seller(db, users["seller"].id).badge == "new_seller"
    for _ in range(3):
        complete_sale(db, users, listing, stars=5)
    t = trust.for_seller(db, users["seller"].id)
    assert (t.completed_sales, t.reviews, t.rating) == (3, 3, D("5.0"))
    assert t.badge in ("bronze", "silver") and 40 <= t.score < 80
    profile = market.seller_profile(db, users["seller"].id)
    assert profile["completed_sales"] == 3 and profile["active_listings"] == 1


def test_lost_dispute_lowers_trust(db, users):
    listing = new_listing(db, users["seller"], quantity=5, price=D("20.00"))
    before = trust.for_seller(db, users["seller"].id).score
    order = market.buy(db, users["buyer"], listing.id, 1)
    escrow.pay(db, users["buyer"], order.id)
    escrow.accept(db, users["seller"], order.id)
    escrow.open_dispute(db, users["buyer"], order.id, "Broken")
    escrow.resolve_dispute(db, users["mediator"], order.id, D("20.00"), "Refund")
    db.commit()
    assert trust.for_seller(db, users["seller"].id).score == before - 10


# ---------- reports and moderation ----------


def test_three_reports_hide_listing_until_moderator_decides(db, users):
    listing = new_listing(db, users["seller"])
    reporters = [make_user(db) for _ in range(3)]
    with pytest.raises(AppError, match="own listing"):
        market.report(db, users["seller"], listing.id, "scam", "")
    market.report(db, reporters[0], listing.id, "scam", "Asked me to pay outside the app")
    db.commit()
    with pytest.raises(Conflict, match="already reported"):
        market.report(db, reporters[0], listing.id, "scam", "")
    db.rollback()
    market.report(db, reporters[1], listing.id, "prohibited", "")
    db.commit()
    assert listing_now(db, listing.id).status == "active"  # two reports: still visible
    market.report(db, reporters[2], listing.id, "scam", "")
    db.commit()
    assert listing_now(db, listing.id).status == "under_review"  # third report hides it
    assert market.search(db, market.SearchFilters()) == []
    moderator = make_user(db, role="moderator")
    market.moderate(db, moderator, listing.id, "restore")
    db.commit()
    assert listing_now(db, listing.id).status == "active"
    assert market.open_reports(db, 50, 0) == []


def test_removed_listing_is_locked(db, users):
    listing = new_listing(db, users["seller"])
    market.moderate(db, make_user(db, role="moderator"), listing.id, "remove")
    db.commit()
    with pytest.raises(Conflict, match="removed"):
        market.update_listing(db, users["seller"], listing.id, listing_input(db))


# ---------- photos and HTTP ----------


def jpeg_with_gps(width=3000, height=2000) -> bytes:
    img = Image.new("RGB", (width, height), (30, 120, 60))
    exif = Image.Exif()
    exif[0x8825] = {2: (9.0, 28.0, 0.0), 4: (147.0, 9.0, 0.0)}  # GPS block (Port Moresby)
    exif[0x010F] = "PhoneMaker"
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_photo_upload_resizes_and_strips_gps(client, db, users):
    seller = users["seller"]
    listing = new_listing(db, seller)
    r = client.post(
        f"/v1/listings/{listing.id}/photos",
        headers=auth(seller),
        files={"file": ("lamp.jpg", jpeg_with_gps(), "image/jpeg")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert max(body["width"], body["height"]) == 1280
    stored = os.path.join(get_settings().media_dir, body["url"].removeprefix("/media/"))
    with Image.open(stored) as img:
        assert max(img.size) == 1280 and not img.getexif()  # no GPS, no camera data
    assert client.get(body["thumb_url"]).headers["cache-control"].startswith("public")
    bad = client.post(
        f"/v1/listings/{listing.id}/photos",
        headers=auth(seller),
        files={"file": ("x.jpg", b"not an image", "image/jpeg")},
    )
    assert bad.json()["error"]["code"] == "photo_invalid"


def test_photo_limit_and_owner_only(client, db, users):
    seller = users["seller"]
    listing = new_listing(db, seller)
    small = jpeg_with_gps(200, 150)
    for _ in range(5):
        assert (
            client.post(
                f"/v1/listings/{listing.id}/photos",
                headers=auth(seller),
                files={"file": ("p.jpg", small, "image/jpeg")},
            ).status_code
            == 201
        )
    sixth = client.post(
        f"/v1/listings/{listing.id}/photos", headers=auth(seller), files={"file": ("p.jpg", small, "image/jpeg")}
    )
    assert sixth.json()["error"]["code"] == "too_many_photos"
    other = client.post(
        f"/v1/listings/{listing.id}/photos",
        headers=auth(users["buyer"]),
        files={"file": ("p.jpg", small, "image/jpeg")},
    )
    assert other.status_code == 403


def test_marketplace_over_http(client, db, users):
    seller, buyer = users["seller"], users["buyer"]
    body = {
        "title": "Bilum, hand made in Goroka",
        "description": "Natural fibre",
        "category_id": cat(db, "bilums"),
        "price": "85.00",
        "quantity": 2,
        "condition": "new",
        "delivery_options": ["seller_delivers"],
        "province_id": loc(db, "Eastern Highlands", "province"),
        "district_id": loc(db, "Goroka", "district"),
    }
    created = client.post("/v1/listings", json=body, headers=auth(seller))
    assert created.status_code == 201, created.text
    listing = created.json()
    assert listing["price"] == "85.00" and listing["province"] == "Eastern Highlands"
    assert listing["seller"]["badge"] == "new_seller"
    # browsing is public
    found = client.get("/v1/listings", params={"q": "bilum", "category": "arts-crafts"}).json()
    assert [x["id"] for x in found] == [listing["id"]]
    assert len(client.get("/v1/locations").json()) == 22
    # buy and pay
    order = client.post(
        f"/v1/listings/{listing['id']}/buy", json={"quantity": 2}, headers={**auth(buyer), "Idempotency-Key": "buy-1"}
    ).json()
    assert order["amount"] == "170.00" and order["listing_id"] == listing["id"]
    paid = client.post(f"/v1/orders/{order['id']}/pay", headers=auth(buyer)).json()
    assert client.get(f"/v1/listings/{listing['id']}").json()["status"] == "sold_out"
    client.post(f"/v1/orders/{order['id']}/accept", headers=auth(seller))
    client.post(f"/v1/orders/{order['id']}/handover", json={"pin": paid["handover_pin"]}, headers=auth(seller))
    rv = client.post(
        f"/v1/orders/{order['id']}/review", json={"stars": 5, "comment": "Beautiful bilum"}, headers=auth(buyer)
    )
    assert rv.status_code == 201
    profile = client.get(f"/v1/sellers/{seller.id}").json()
    assert profile["rating"] == "5.0" and profile["completed_sales"] == 1
    assert integrity_report(db)["ok"]


def test_paused_listing_visibility(client, db, users):
    listing = new_listing(db, users["seller"])
    client.post(f"/v1/listings/{listing.id}/status", json={"status": "paused"}, headers=auth(users["seller"]))
    assert client.get(f"/v1/listings/{listing.id}").status_code == 404
    assert client.get(f"/v1/listings/{listing.id}", headers=auth(users["seller"])).json()["status"] == "paused"


def test_moderation_endpoints_need_moderator(client, db, users):
    assert client.get("/v1/mod/reports", headers=auth(users["buyer"])).status_code == 403
    moderator = make_user(db, role="moderator")
    assert client.get("/v1/mod/reports", headers=auth(moderator)).status_code == 200
    trust_raw = client.get(f"/v1/mod/sellers/{users['seller'].id}/trust", headers=auth(moderator)).json()
    assert "score" in trust_raw


def test_profile_store_name(client, db, users):
    r = client.put(
        "/v1/me/profile",
        json={"display_name": "Kila", "store_name": "Kila Solar Supplies", "bio": "Solar lights, Lae"},
        headers=auth(users["seller"]),
    )
    assert r.status_code == 200
    assert client.get(f"/v1/sellers/{users['seller'].id}").json()["name"] == "Kila Solar Supplies"

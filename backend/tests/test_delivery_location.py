"""Delivery / meet-up location (M3.1): GPS point first, address as the second identifier."""

from decimal import Decimal as D

import pytest

from app.errors import AppError, Conflict, NotFound
from app.marketplace import service as market
from tests.conftest import auth, make_user
from tests.test_marketplace import new_listing

ERIKU = (D("-6.72900"), D("146.99700"))


def test_listing_meetup_point_defaults_order_location(db):
    seller, buyer = make_user(db, tier=2), make_user(db, tier=1)
    listing = new_listing(db, seller, latitude=ERIKU[0], longitude=ERIKU[1], meetup_address="Eriku market gate")
    order = market.buy(db, buyer, listing.id, 1)
    assert order.delivery_method == "meetup"
    assert (order.delivery_latitude, order.delivery_longitude) == ERIKU
    assert order.delivery_address == "Eriku market gate"


def test_delivery_to_buyer_needs_a_location(db):
    seller, buyer = make_user(db, tier=2), make_user(db, tier=1)
    listing = new_listing(db, seller, delivery_options=["meetup", "seller_delivers"])
    with pytest.raises(AppError, match="delivery location"):
        market.buy(db, buyer, listing.id, 1, market.DeliveryPlace("seller_delivers"))
    with pytest.raises(AppError, match="does not offer"):
        market.buy(db, buyer, listing.id, 1, market.DeliveryPlace("courier", address="Taraka"))
    by_address = market.buy(
        db, buyer, listing.id, 1, market.DeliveryPlace("seller_delivers", address="Blue house, Taraka")
    )
    assert by_address.delivery_latitude is None and by_address.delivery_address == "Blue house, Taraka"
    by_gps = market.buy(
        db, buyer, listing.id, 1, market.DeliveryPlace("seller_delivers", D("-6.70100"), D("146.98500"))
    )
    assert by_gps.delivery_latitude == D("-6.70100")


def test_point_needs_both_coordinates(db):
    seller = make_user(db, tier=2)
    with pytest.raises(AppError, match="both latitude and longitude"):
        new_listing(db, seller, latitude=ERIKU[0])


def test_parties_can_move_the_meeting_point_until_closed(db):
    seller, buyer, stranger = make_user(db, tier=2), make_user(db, tier=1), make_user(db, tier=1)
    listing = new_listing(db, seller, latitude=ERIKU[0], longitude=ERIKU[1])
    order = market.buy(db, buyer, listing.id, 1)
    db.commit()
    moved = market.set_delivery_place(db, seller, order.id, D("-6.73000"), D("147.00000"), "BSP ATM, Eriku")
    assert moved.delivery_address == "BSP ATM, Eriku" and moved.delivery_longitude == D("147.00000")
    with pytest.raises(NotFound):
        market.set_delivery_place(db, stranger, order.id, None, None, "somewhere")
    with pytest.raises(AppError, match="GPS point or an address"):
        market.set_delivery_place(db, buyer, order.id, None, None, "  ")
    db.rollback()
    from app.escrow import service as escrow

    escrow.cancel(db, buyer, order.id, "changed my mind")
    db.commit()
    with pytest.raises(Conflict, match="closed"):
        market.set_delivery_place(db, buyer, order.id, None, None, "too late")


def test_delivery_over_http(client, db):
    seller, buyer = make_user(db, tier=2), make_user(db, tier=1)
    listing = new_listing(
        db,
        seller,
        latitude=ERIKU[0],
        longitude=ERIKU[1],
        meetup_address="Eriku market gate",
        delivery_options=["meetup", "courier"],
    )
    shown = client.get(f"/v1/listings/{listing.id}").json()
    assert shown["meetup"] == {"latitude": "-6.72900", "longitude": "146.99700", "address": "Eriku market gate"}
    body = {
        "quantity": 1,
        "delivery": {
            "method": "courier",
            "latitude": "-6.70100",
            "longitude": "146.98500",
            "address": "Taraka, gate 2",
        },
    }
    order = client.post(
        f"/v1/listings/{listing.id}/buy", json=body, headers={**auth(buyer), "Idempotency-Key": "buy-loc-1"}
    ).json()
    assert order["delivery_method"] == "courier" and order["delivery_address"] == "Taraka, gate 2"
    assert order["delivery_latitude"] == "-6.70100"
    outside_png = {"latitude": "-33.86000", "longitude": "151.20000"}  # Sydney
    r = client.post(f"/v1/orders/{order['id']}/delivery-location", json=outside_png, headers=auth(seller))
    assert r.status_code == 422
    r = client.post(
        f"/v1/orders/{order['id']}/delivery-location", json={"address": "Meet at Eriku BSP"}, headers=auth(seller)
    )
    assert r.status_code == 200 and r.json()["delivery_address"] == "Meet at Eriku BSP"

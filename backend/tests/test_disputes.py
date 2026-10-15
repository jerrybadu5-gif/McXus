"""Three-stage disputes (ADR 0011): negotiate 3 days -> mediator 5 PNG working days -> appeal 3 days -> senior."""

import io
from datetime import UTC, date, datetime
from decimal import Decimal as D

import pytest
from PIL import Image

from app.disputes import service as disputes
from app.disputes.calendar import add_working_days, easter, holidays
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.escrow import service as escrow
from app.jobs import run_timers
from app.models import Dispute
from tests.conftest import auth, make_user
from tests.test_escrow import assert_books_ok, balance, paid_order


@pytest.fixture
def dispute(db, users):
    """A K200 order, dispatched, that the buyer disputes."""
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    escrow.dispatch(db, users["seller"], order.id)
    disputes.open_dispute(db, users["buyer"], order.id, "The lamp arrived cracked")
    db.commit()
    return order


def stage(db, order):
    db.expire_all()
    return db.query(Dispute).filter_by(order_id=order.id).one().status


def photo_bytes() -> bytes:
    out = io.BytesIO()
    img = Image.new("RGB", (2000, 1500), (200, 80, 40))
    exif = Image.Exif()
    exif[0x8825] = {2: (9.0, 26.0, 0.0)}  # a GPS block, as phone photos carry
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


# ---------- calendar ----------


def test_png_working_days():
    assert easter(2026) == date(2026, 4, 5)
    h = holidays(2026)
    assert {date(2026, 4, 3), date(2026, 4, 6), date(2026, 6, 8), date(2026, 9, 16), date(2026, 12, 25)} <= h
    # Mon 14 Sep 2026 + 5 working days skips Independence Day (Wed 16th) and the weekend -> Tue 22 Sep, 17:00 PNG.
    start = datetime(2026, 9, 14, 1, 0, tzinfo=UTC)  # 11:00 in Port Moresby
    assert add_working_days(start, 5) == datetime(2026, 9, 22, 7, 0, tzinfo=UTC)


# ---------- stage 1 ----------


def test_agreed_offer_settles_at_once(db, users, dispute):
    view = disputes.view(db, users["buyer"], dispute.id)
    assert view["stage"] == "negotiation" and {"offer", "escalate", "statement", "photo"} <= set(view["actions"])
    assert view["evidence"][0]["text"] == "The lamp arrived cracked"
    offer = disputes.make_offer(db, users["seller"], dispute.id, D("50.00"), "Sorry, half the shade is fine")
    db.commit()
    with pytest.raises(Conflict, match="own offer"):
        disputes.answer_offer(db, users["seller"], dispute.id, offer.id, True)
    disputes.answer_offer(db, users["buyer"], dispute.id, offer.id, True)
    db.commit()
    assert stage(db, dispute) == "resolved"
    assert dispute.status == "RESOLVED"
    assert balance(db, users["buyer"]) == D("350.00")
    assert balance(db, users["seller"]) == D("145.50")  # 150 less 3% escrow fee
    resolved = disputes.view(db, users["seller"], dispute.id)["resolution"]
    assert (resolved["outcome"], resolved["buyer_refund"], resolved["seller_gets"]) == (
        "agreed",
        D("50.00"),
        D("150.00"),
    )
    assert_books_ok(db)


def test_offer_rules(db, users, dispute):
    stranger = make_user(db)
    with pytest.raises(Forbidden):
        disputes.make_offer(db, stranger, dispute.id, D("10.00"))
    with pytest.raises(AppError, match="between K0 and K200"):
        disputes.make_offer(db, users["buyer"], dispute.id, D("250.00"))
    first = disputes.make_offer(db, users["buyer"], dispute.id, D("200.00"))
    second = disputes.make_offer(db, users["buyer"], dispute.id, D("150.00"))
    db.commit()
    assert first.status == "replaced"
    disputes.answer_offer(db, users["seller"], dispute.id, second.id, False)
    db.commit()
    assert second.status == "rejected"
    with pytest.raises(Conflict, match="rejected"):
        disputes.answer_offer(db, users["seller"], dispute.id, second.id, True)
    third = disputes.make_offer(db, users["buyer"], dispute.id, D("120.00"))
    disputes.answer_offer(db, users["buyer"], dispute.id, third.id, False)  # the maker withdraws
    assert third.status == "withdrawn"
    assert stage(db, dispute) == "negotiation"


# ---------- stage 2 and 3 ----------


def test_no_agreement_goes_to_mediator_then_appeal_then_senior(db, users, dispute, fake_clock):
    senior = make_user(db, role="compliance", name="senior")
    fake_clock.advance(days=3)
    assert run_timers() == {"dispute_mediation": 1}
    db.expire_all()
    d = db.query(Dispute).filter_by(order_id=dispute.id).one()
    assert d.status == "mediation" and d.mediator_due is not None
    # Opened Wed 14 Oct 2026 00:00 UTC; escalated Sat 17 Oct -> 5 working days -> Fri 23 Oct 17:00 PNG.
    assert d.mediator_due == datetime(2026, 10, 23, 7, 0, tzinfo=UTC)

    with pytest.raises(Forbidden):
        disputes.decide(db, users["buyer"], dispute.id, D("200.00"), "I decide myself")
    disputes.add_statement(db, users["seller"], dispute.id, "It was packed in bubble wrap")
    disputes.take_case(db, users["mediator"], dispute.id)
    disputes.decide(db, users["mediator"], dispute.id, D("80.00"), "Shade cracked in transit; partial refund")
    db.commit()
    assert stage(db, dispute) == "decided"
    assert dispute.status == "DISPUTED"  # no money moves during the appeal window
    view = disputes.view(db, users["seller"], dispute.id)
    assert {"accept_decision", "appeal"} <= set(view["actions"])

    disputes.appeal(db, users["seller"], dispute.id, "The buyer dropped it, see my photos")
    db.commit()
    assert stage(db, dispute) == "appeal"
    with pytest.raises(Forbidden):  # the mediator who decided cannot hear the appeal
        disputes.final_decision(db, users["mediator"], dispute.id, D("0.00"), "No refund")
    disputes.final_decision(db, senior, dispute.id, D("40.00"), "Shared fault: K40 back to the buyer")
    db.commit()
    assert stage(db, dispute) == "resolved"
    assert balance(db, users["buyer"]) == D("340.00")
    resolution = disputes.view(db, users["buyer"], dispute.id)["resolution"]
    assert resolution["outcome"] == "senior"
    assert_books_ok(db)


def test_decision_becomes_final_after_the_appeal_window(db, users, dispute, fake_clock):
    disputes.escalate(db, users["buyer"], dispute.id)
    disputes.decide(db, users["mediator"], dispute.id, D("200.00"), "Item not as described: full refund")
    db.commit()
    fake_clock.advance(days=2)
    assert run_timers() == {}
    fake_clock.advance(days=1, seconds=1)
    assert run_timers() == {"dispute_resolved": 1}
    assert stage(db, dispute) == "resolved"
    assert balance(db, users["buyer"]) == D("500.00")
    with pytest.raises(Conflict, match="resolved"):
        disputes.appeal(db, users["seller"], dispute.id, "Too late now")


def test_both_accepting_ends_it_early(db, users, dispute):
    disputes.escalate(db, users["seller"], dispute.id)
    disputes.decide(db, users["mediator"], dispute.id, D("100.00"), "Half each")
    disputes.accept_decision(db, users["buyer"], dispute.id)
    db.commit()
    assert stage(db, dispute) == "decided"
    with pytest.raises(Conflict, match="already accepted"):
        disputes.appeal(db, users["buyer"], dispute.id, "Changed my mind")
    disputes.accept_decision(db, users["seller"], dispute.id)
    db.commit()
    assert stage(db, dispute) == "resolved"
    assert balance(db, users["seller"]) == D("97.00")


def test_mediator_who_is_a_party_cannot_decide(db, users):
    mediator_seller = make_user(db, role="mediator")
    order = escrow.create_order(db, users["buyer"], mediator_seller.id, "Phone", D("50.00"))
    escrow.pay(db, users["buyer"], order.id)
    escrow.accept(db, mediator_seller, order.id)
    disputes.open_dispute(db, users["buyer"], order.id, "Wrong colour")
    disputes.escalate(db, users["buyer"], order.id)
    with pytest.raises(Forbidden, match="part of"):
        disputes.decide(db, mediator_seller, order.id, D("0.00"), "Mine is fine")


# ---------- evidence and the API ----------


def test_photos_lose_metadata_and_are_private(client, db, users, dispute):
    buyer, seller = auth(users["buyer"]), auth(users["seller"])
    r = client.post(
        f"/v1/disputes/{dispute.id}/photos",
        headers=buyer,
        files={"file": ("crack.jpg", photo_bytes(), "image/jpeg")},
        params={"caption": "The crack"},
    )
    assert r.status_code == 201, r.text
    photo = [e for e in r.json()["evidence"] if e["kind"] == "photo"][0]
    assert photo["width"] == 1280 and photo["text"] == "The crack"
    data = client.get(photo["file"], headers=seller)  # the other party can see it
    assert data.status_code == 200 and data.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(data.content)) as img:
        assert 0x8825 not in img.getexif()  # GPS gone
    stranger = make_user(db)
    assert client.get(photo["file"], headers=auth(stranger)).status_code == 404
    assert client.get(photo["file"], headers=auth(users["mediator"])).status_code == 200
    for _ in range(4):
        client.post(f"/v1/disputes/{dispute.id}/photos", headers=buyer, files={"file": ("x.jpg", photo_bytes())})
    r = client.post(f"/v1/disputes/{dispute.id}/photos", headers=buyer, files={"file": ("x.jpg", photo_bytes())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "too_many_photos"
    with pytest.raises(NotFound):
        disputes.view(db, stranger, dispute.id)


def test_api_flow_and_staff_queue(client, db, users, dispute, fake_clock):
    buyer, seller, mediator = auth(users["buyer"]), auth(users["seller"]), auth(users["mediator"])
    other, _ = paid_order(db, users, "40.00")
    escrow.accept(db, users["seller"], other.id)
    db.commit()
    r = client.post(f"/v1/orders/{other.id}/dispute", headers=seller, json={"reason": "Buyer never came to meet"})
    assert r.status_code == 200 and r.json()["stage"] == "negotiation" and r.json()["you"] == "seller"

    r = client.post(f"/v1/disputes/{dispute.id}/offers", headers=seller, json={"buyer_refund": "30.00"})
    assert r.status_code == 201
    offer = r.json()["offers"][0]
    assert offer["by"] == "seller" and offer["buyer_refund"] == "30.00"
    assert client.post(f"/v1/disputes/{dispute.id}/escalate", headers=buyer).json()["stage"] == "mediation"
    assert client.get(f"/v1/disputes/{dispute.id}", headers=buyer).json()["offers"][0]["status"] == "open"

    assert client.get("/v1/admin/disputes", headers=buyer).status_code == 403
    fake_clock.advance(days=10)  # the mediator deadline has passed: overdue first
    queue = client.get("/v1/admin/disputes", headers=mediator).json()
    assert [q["order_id"] for q in queue][0] == str(dispute.id) and queue[0]["overdue"] is True
    assert queue[1]["overdue"] is False  # negotiation deadlines are handled by the worker, not staff
    assert client.get("/v1/admin/disputes/counts", headers=mediator).json() == {"mediation": 1, "negotiation": 1}

    r = client.post(
        f"/v1/admin/disputes/{dispute.id}/decide",
        headers=mediator,
        json={"buyer_refund": "60.00", "note": "Partial refund for the crack"},
    )
    assert r.status_code == 200 and r.json()["stage"] == "decided"
    assert r.json()["decision"]["buyer_refund"] == "60.00"
    assert client.get(f"/v1/disputes/{dispute.id}", headers=buyer).json()["offers"][0]["status"] == "lapsed"
    r = client.post(f"/v1/disputes/{dispute.id}/appeal", headers=buyer, json={"reason": "The whole lamp is broken"})
    assert r.json()["stage"] == "appeal" and r.json()["appeal"]["by"] == "buyer"
    r = client.post(
        f"/v1/admin/disputes/{dispute.id}/final",
        headers=mediator,
        json={"buyer_refund": "200.00", "note": "Full refund"},
    )
    assert r.status_code == 403  # mediators can't decide appeals
    mine = client.get("/v1/disputes", headers=buyer).json()
    assert {m["stage"] for m in mine} == {"appeal", "negotiation"}  # the worker has not run here
    timeline = client.get(f"/v1/disputes/{dispute.id}", headers=seller).json()["timeline"]
    assert [t["kind"] for t in timeline] == ["opened", "offer", "escalated", "decided", "appealed"]

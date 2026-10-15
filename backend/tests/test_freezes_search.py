"""M4.1: freezing with appeals and two-person unfreeze; case-insensitive search; dispute 'needs you' alerts."""

from decimal import Decimal as D

from app.disputes import service as disputes
from app.escrow import service as escrow
from tests.conftest import auth, make_user
from tests.test_escrow import paid_order


def test_freeze_appeal_and_unfreeze_by_another_person(client, db, users):
    cora = make_user(db, role="compliance", name="Cora")
    admin = make_user(db, role="admin", name="Ada")
    seller = users["seller"]
    r = client.post(
        f"/v1/admin/users/{seller.id}/status",
        headers=auth(cora),
        json={"status": "frozen", "reason": "Three buyers report fake phones"},
    )
    assert r.status_code == 200 and r.json()["status"] == "frozen"

    # The frozen person can still sign in, sees why, and can appeal once; nothing else works.
    me = client.get("/v1/me", headers=auth(seller))
    assert me.status_code == 200 and me.json()["status"] == "frozen"
    assert client.get("/v1/wallet", headers=auth(seller)).json()["error"]["code"] == "account_frozen"
    case = client.get("/v1/me/freeze", headers=auth(seller)).json()
    assert case["reason"] == "Three buyers report fake phones" and case["can_appeal"] is True
    r = client.post(
        "/v1/me/freeze/appeal", headers=auth(seller), json={"text": "Those were real phones, here are receipts"}
    )
    assert r.status_code == 200 and r.json()["status"] == "appealed"
    again = client.post("/v1/me/freeze/appeal", headers=auth(seller), json={"text": "Please look again at my case"})
    assert again.json()["error"]["code"] == "already_appealed"

    listed = client.get("/v1/admin/freezes", headers=auth(cora)).json()
    assert [(c["user"]["id"], c["status"], c["frozen_by"]) for c in listed] == [(str(seller.id), "appealed", "Cora")]
    case_id = listed[0]["id"]
    # The person who froze it cannot decide; someone else must.
    r = client.post(
        f"/v1/admin/freezes/{case_id}/decide", headers=auth(cora), json={"unfreeze": True, "note": "Receipts check out"}
    )
    assert r.json()["error"]["code"] == "same_person"
    r = client.post(
        f"/v1/admin/freezes/{case_id}/decide",
        headers=auth(admin),
        json={"unfreeze": True, "note": "Receipts check out"},
    )
    assert r.status_code == 200 and r.json()["status"] == "unfrozen" and r.json()["decided_by"] == "Ada"
    assert client.get("/v1/wallet", headers=auth(seller)).status_code == 200
    assert client.get("/v1/me/freeze", headers=auth(seller)).json()["decision_note"] == "Receipts check out"
    assert client.get("/v1/admin/freezes", headers=auth(cora)).json() == []
    assert [c["status"] for c in client.get("/v1/admin/freezes?status=closed", headers=auth(cora)).json()] == [
        "unfrozen"
    ]
    actions = [e["action"] for e in client.get("/v1/admin/audit", headers=auth(admin)).json()]
    assert actions[:2] == ["user_active", "user_frozen"]


def test_refused_appeal_keeps_account_frozen(client, db, users):
    cora = make_user(db, role="compliance", name="Cora")
    second = make_user(db, role="compliance", name="Sam")
    buyer = users["buyer"]
    client.post(
        f"/v1/admin/users/{buyer.id}/status",
        headers=auth(cora),
        json={"status": "frozen", "reason": "Chargeback fraud"},
    )
    case_id = client.get("/v1/admin/freezes", headers=auth(cora)).json()[0]["id"]
    r = client.post(
        f"/v1/admin/freezes/{case_id}/decide", headers=auth(second), json={"unfreeze": False, "note": "No appeal yet"}
    )
    assert r.json()["error"]["code"] == "no_appeal"  # nothing to refuse until the person appeals
    client.post("/v1/me/freeze/appeal", headers=auth(buyer), json={"text": "It was my cousin using my phone"})
    r = client.post(
        f"/v1/admin/freezes/{case_id}/decide",
        headers=auth(second),
        json={"unfreeze": False, "note": "The bank confirmed the chargeback"},
    )
    assert r.json()["status"] == "upheld"
    assert client.get("/v1/me", headers=auth(buyer)).json()["status"] == "frozen"
    mine = client.get("/v1/me/freeze", headers=auth(buyer)).json()
    assert mine["can_appeal"] is False and mine["decision_note"] == "The bank confirmed the chargeback"
    # Staff can still unfreeze later (e.g. new information), again with a note.
    r = client.post(
        f"/v1/admin/users/{buyer.id}/status", headers=auth(second), json={"status": "active", "reason": "Repaid"}
    )
    assert r.json()["error"]["code"] == "not_frozen"  # the upheld case is closed; freeze again to reopen
    overview = client.get("/v1/admin/overview", headers=auth(cora)).json()
    assert overview["freezes_open"] == 0 and overview["freeze_appeals"] == 0


def test_search_is_not_case_sensitive_and_suggests(client, db, users):
    staff = auth(make_user(db, role="support", name="Desk"))
    make_user(db, name="Mama Ruth Kila")
    for q in ["mama ruth", "RUTH", "kila mama", "Ru"]:
        names = [u["display_name"] for u in client.get("/v1/admin/users", headers=staff, params={"q": q}).json()]
        assert "Mama Ruth Kila" in names, q
    # Customers: names from 2 letters, phones only when almost complete; never themselves, never frozen accounts.
    me = auth(users["buyer"])
    found = client.get("/v1/users/search", headers=me, params={"q": "SELL"}).json()
    assert [(p["name"], p["phone_hint"]) for p in found] == [("seller", "…" + users["seller"].phone[-3:])]
    assert client.get("/v1/users/search", headers=me, params={"q": "s"}).json() == []
    assert client.get("/v1/users/search", headers=me, params={"q": users["seller"].phone[-4:]}).json() == []
    assert len(client.get("/v1/users/search", headers=me, params={"q": users["seller"].phone[-8:]}).json()) == 1
    assert client.get("/v1/users/search", headers=me, params={"q": "buyer"}).json() == []


def test_dispute_attention_for_the_other_party(client, db, users):
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    db.commit()
    buyer, seller = auth(users["buyer"]), auth(users["seller"])
    client.post(f"/v1/orders/{order.id}/dispute", headers=buyer, json={"reason": "Wrong colour sent"})
    att = client.get("/v1/disputes/attention", headers=seller).json()
    assert att["count"] == 1 and att["items"][0]["attention"].startswith("The buyer opened a dispute")
    assert client.get("/v1/disputes/attention", headers=buyer).json()["count"] == 0
    first = att["items"][0]["last_event"]

    client.post(f"/v1/disputes/{order.id}/offers", headers=seller, json={"buyer_refund": "50.00"})
    assert client.get("/v1/disputes/attention", headers=seller).json()["count"] == 0
    att = client.get("/v1/disputes/attention", headers=buyer).json()
    assert att["items"][0]["attention"] == "The seller offered: buyer gets back K50.00"
    assert att["items"][0]["last_event"] > first  # a new event: the app notifies again
    assert client.get("/v1/disputes", headers=buyer).json()[0]["attention"].startswith("The seller offered")

    client.post(f"/v1/disputes/{order.id}/escalate", headers=buyer)
    disputes.decide(db, users["mediator"], order.id, D("100.00"), "Half back for the colour")
    db.commit()
    for who in (buyer, seller):
        assert (
            client.get("/v1/disputes/attention", headers=who).json()["items"][0]["attention"]
            == "The mediator decided: accept or appeal"
        )
    client.post(f"/v1/disputes/{order.id}/accept-decision", headers=buyer)
    assert client.get("/v1/disputes/attention", headers=buyer).json()["count"] == 0
    assert client.get("/v1/disputes/attention", headers=seller).json()["count"] == 1

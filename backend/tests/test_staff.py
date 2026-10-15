"""Staff console API (M4): search, profile, freeze, order lookup, overview, audit trail."""

from decimal import Decimal as D

from app.disputes import service as disputes
from app.escrow import service as escrow
from tests.conftest import auth, make_user
from tests.test_escrow import paid_order


def test_search_profile_and_names(client, db, users):
    support = make_user(db, role="support", name="Support Sam")
    staff = auth(support)
    order, _ = paid_order(db, users)
    escrow.accept(db, users["seller"], order.id)
    disputes.open_dispute(db, users["buyer"], order.id, "Never arrived")
    db.commit()

    assert client.get("/v1/admin/users", headers=auth(users["buyer"])).status_code == 403
    found = client.get("/v1/admin/users", headers=staff, params={"q": "buyer"}).json()
    assert [u["id"] for u in found] == [str(users["buyer"].id)]
    by_phone = client.get("/v1/admin/users", headers=staff, params={"q": users["seller"].phone[-7:]}).json()
    assert [u["id"] for u in by_phone] == [str(users["seller"].id)]
    staff_list = client.get("/v1/admin/users", headers=staff, params={"role": "staff"}).json()
    assert {u["role"] for u in staff_list} == {"support", "mediator", "finance"}

    profile = client.get(f"/v1/admin/users/{users['buyer'].id}", headers=staff).json()
    assert profile["wallet"] == "300.00" and profile["orders_as_buyer"] == 1 and profile["disputes"] == 1
    names = client.get("/v1/admin/users/names", headers=staff, params={"ids": [str(users["seller"].id)]}).json()
    assert names == {str(users["seller"].id): "seller"}

    orders = client.get("/v1/admin/orders", headers=staff, params={"status": "DISPUTED"}).json()
    assert [o["id"] for o in orders] == [str(order.id)]
    assert client.get("/v1/admin/orders", headers=staff, params={"q": "lamp"}).json()[0]["id"] == str(order.id)

    overview = client.get("/v1/admin/overview", headers=staff).json()
    assert overview["disputes"] == {"negotiation": 1} and overview["role"] == "support"
    assert overview["staff"] == 4


def test_freeze_needs_compliance_and_is_logged(client, db, users):
    compliance = make_user(db, role="compliance", name="Cora")
    target = users["seller"]
    r = client.post(
        f"/v1/admin/users/{target.id}/status",
        headers=auth(users["mediator"]),
        json={"status": "frozen", "reason": "Fraud report"},
    )
    assert r.status_code == 403
    r = client.post(
        f"/v1/admin/users/{target.id}/status",
        headers=auth(compliance),
        json={"status": "frozen", "reason": "Fraud report from three buyers"},
    )
    assert r.status_code == 200 and r.json()["status"] == "frozen"
    assert client.get("/v1/wallet", headers=auth(target)).status_code in (401, 403)  # frozen accounts are locked out

    kyc = make_user(db, role="kyc", name="Kim")
    r = client.post(
        f"/v1/admin/users/{users['buyer'].id}/kyc-tier",
        headers=auth(kyc),
        json={"kyc_tier": 1, "note": "ID did not match"},
    )
    assert r.status_code == 200
    log = client.get("/v1/admin/audit", headers=auth(compliance)).json()
    assert [(e["action"], e["actor"]) for e in log] == [("kyc_tier", "Kim"), ("user_frozen", "Cora")]
    assert log[0]["detail"] == "2 -> 1. ID did not match"
    assert client.get("/v1/admin/audit", headers=auth(kyc)).status_code == 403


def test_dispute_decisions_are_logged(client, db, users):
    order, _ = paid_order(db, users, "80.00")
    escrow.accept(db, users["seller"], order.id)
    disputes.open_dispute(db, users["buyer"], order.id, "Wrong size")
    db.commit()
    mediator = auth(users["mediator"])
    client.post(f"/v1/admin/disputes/{order.id}/take", headers=mediator)
    client.post(
        f"/v1/admin/disputes/{order.id}/decide",
        headers=mediator,
        json={"buyer_refund": "80.00", "note": "Seller sent the wrong size"},
    )
    admin = make_user(db, role="admin")
    log = client.get("/v1/admin/audit", headers=auth(admin), params={"target_id": str(order.id)}).json()
    assert [e["action"] for e in log] == ["dispute_decided", "dispute_taken"]
    assert log[0]["detail"].startswith("Buyer gets back K80.00")
    assert (
        D(client.get(f"/v1/disputes/{order.id}", headers=auth(users["buyer"])).json()["decision"]["buyer_refund"]) == 80
    )

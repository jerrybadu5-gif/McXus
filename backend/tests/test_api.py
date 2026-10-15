import uuid

from app.auth import service as auth_service
from app.models import JournalEntry
from tests.conftest import auth, make_user


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "sandbox": True, "api_level": 6}


def test_phone_sign_in_flow(client, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(auth_service, "send_sms", lambda phone, text: sent.append(text))
    assert client.post("/v1/auth/otp/request", json={"phone": "071234567"}).status_code == 202
    code = sent[0].split("code is ")[1][:6]
    bad = client.post(
        "/v1/auth/otp/verify", json={"phone": "71234567", "code": "000000" if code != "000000" else "111111"}
    )
    assert bad.status_code == 401
    ok = client.post("/v1/auth/otp/verify", json={"phone": "+67571234567", "code": code})
    assert ok.status_code == 200
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"}).json()
    assert me["phone"] == "+67571234567" and me["kyc_tier"] == 0
    # the code cannot be reused
    assert client.post("/v1/auth/otp/verify", json={"phone": "71234567", "code": code}).status_code == 401


def test_otp_rate_limit(client, monkeypatch):
    monkeypatch.setattr(auth_service, "send_sms", lambda *_: None)
    codes = [client.post("/v1/auth/otp/request", json={"phone": "71234568"}).status_code for _ in range(4)]
    assert codes == [202, 202, 202, 429]


def test_invalid_phone(client):
    r = client.post("/v1/auth/otp/request", json={"phone": "12345"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_phone"


def test_requires_sign_in(client):
    assert client.get("/v1/wallet").status_code == 401


def test_money_is_returned_as_exact_strings(client, db):
    user = make_user(db, stars=12)
    body = client.get("/v1/wallet", headers=auth(user)).json()
    assert body["balance"] == "12.00"


def test_idempotent_topup_moves_money_once(client, db):
    user = make_user(db)
    headers = {**auth(user), "Idempotency-Key": str(uuid.uuid4())}
    first = client.post("/v1/wallet/sandbox-topup", json={"amount": "100.00"}, headers=headers)
    retry = client.post("/v1/wallet/sandbox-topup", json={"amount": "100.00"}, headers=headers)
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert client.get("/v1/wallet", headers=auth(user)).json()["balance"] == "100.00"
    other = client.post("/v1/wallet/sandbox-topup", json={"amount": "5.00"}, headers=headers)
    assert other.json()["error"]["code"] == "idempotency_key_reused"
    missing = client.post("/v1/wallet/sandbox-topup", json={"amount": "5.00"}, headers=auth(user))
    assert missing.json()["error"]["code"] == "idempotency_key_required"


def test_amount_validation(client, db):
    user = make_user(db)
    headers = {**auth(user), "Idempotency-Key": "k1"}
    for bad in ("-5", "0", "10.001", "abc"):
        assert client.post("/v1/wallet/sandbox-topup", json={"amount": bad}, headers=headers).status_code == 422


def test_full_order_flow_over_http(client, db, users):
    buyer, seller = users["buyer"], users["seller"]
    order = client.post(
        "/v1/orders",
        json={"seller_id": str(seller.id), "title": "Bilum bag", "amount": "80.00"},
        headers={**auth(buyer), "Idempotency-Key": "order-1"},
    ).json()
    paid = client.post(f"/v1/orders/{order['id']}/pay", headers=auth(buyer)).json()
    pin = paid["handover_pin"]
    assert paid["order"]["status"] == "FUNDED" and len(pin) == 6
    # the seller never sees the PIN
    assert "handover_pin" not in client.get(f"/v1/orders/{order['id']}", headers=auth(seller)).json()
    assert client.post(f"/v1/orders/{order['id']}/accept", headers=auth(seller)).json()["status"] == "ACCEPTED"
    done = client.post(f"/v1/orders/{order['id']}/handover", json={"pin": pin}, headers=auth(seller)).json()
    assert done["status"] == "RELEASED" and done["seller_paid"] == "77.60" and done["fee_charged"] == "2.40"
    statement = client.get("/v1/wallet/statement", headers=auth(seller)).json()
    assert statement[0]["amount"] == "77.60"
    events = client.get(f"/v1/orders/{order['id']}/events", headers=auth(buyer)).json()
    assert [e["to_status"] for e in events] == ["CREATED", "FUNDED", "ACCEPTED", "RELEASED"]
    kinds = sorted(k for (k,) in db.query(JournalEntry.kind).filter(JournalEntry.order_id == uuid.UUID(order["id"])))
    assert kinds == ["order_fund", "order_release"]


def test_strangers_cannot_see_orders(client, db, users):
    order = client.post(
        "/v1/orders",
        json={"seller_id": str(users["seller"].id), "title": "Kina shell", "amount": "5.00"},
        headers={**auth(users["buyer"]), "Idempotency-Key": "o"},
    ).json()
    stranger = make_user(db)
    assert client.get(f"/v1/orders/{order['id']}", headers=auth(stranger)).status_code == 404


def test_staff_roles_enforced(client, db, users):
    buyer = users["buyer"]
    assert client.get("/v1/admin/reports/integrity", headers=auth(buyer)).status_code == 403
    assert (
        client.post(f"/v1/admin/users/{buyer.id}/role", json={"role": "admin"}, headers=auth(buyer)).status_code == 403
    )
    report = client.get("/v1/admin/reports/integrity", headers=auth(users["finance_a"])).json()
    assert report["ok"] is True
    recon = client.get("/v1/admin/reports/trust-reconciliation", headers=auth(users["finance_a"])).json()
    assert recon["safeguarding_position"] == "0.00"


def test_deposit_maker_checker_over_http(client, users):
    body = {"user_id": str(users["buyer"].id), "amount": "50.00", "method": "bank_transfer", "external_ref": "KINA-778"}
    dep = client.post("/v1/admin/deposits", json=body, headers=auth(users["finance_a"])).json()
    same = client.post(
        f"/v1/admin/deposits/{dep['id']}/decision", json={"approve": True}, headers=auth(users["finance_a"])
    )
    assert same.status_code == 403 and same.json()["error"]["code"] == "maker_checker"
    ok = client.post(
        f"/v1/admin/deposits/{dep['id']}/decision", json={"approve": True}, headers=auth(users["finance_b"])
    )
    assert ok.json()["status"] == "approved"
    assert client.get("/v1/wallet", headers=auth(users["buyer"])).json()["balance"] == "550.00"


def test_sandbox_returns_dev_code(client, monkeypatch):
    monkeypatch.setattr(auth_service, "send_sms", lambda *_: None)
    body = client.post("/v1/auth/otp/request", json={"phone": "71230000"}).json()
    assert len(body["dev_code"]) == 6
    ok = client.post("/v1/auth/otp/verify", json={"phone": "71230000", "code": body["dev_code"]})
    assert ok.status_code == 200

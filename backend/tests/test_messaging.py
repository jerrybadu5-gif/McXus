"""Messaging delivery service (M3): the server stores and relays opaque MLS bytes only."""

import base64
import threading
from datetime import timedelta

import pytest

from app.errors import AppError, Conflict, NotFound
from app.jobs import purge_messages
from app.messaging import service as chat
from app.models import MlsMessage
from tests.conftest import auth, make_user


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.fixture
def pair(db):
    alice, bob = make_user(db, tier=0, name="Alice"), make_user(db, tier=0, name="Bob")
    a_dev = chat.register_device(db, alice, "A phone")
    b_dev = chat.register_device(db, bob, "B phone")
    chat.upload_key_packages(db, bob, b_dev.id, [b64(b"bob-kp-1"), b64(b"bob-kp-2")])
    db.commit()
    return alice, bob, a_dev, b_dev


def start_chat(db, alice, bob, a_dev):
    conv = chat.open_direct(db, alice, bob.id, None)
    chat.post_welcome(db, alice, a_dev.id, conv.id, bob.id, b64(b"welcome-for-bob"))
    db.commit()
    return conv


def test_key_packages_are_claimed_once_each(db, pair):
    alice, bob, _, b_dev = pair
    first = chat.claim_key_package(db, alice, bob.id)
    second = chat.claim_key_package(db, alice, bob.id)
    db.commit()
    assert {first.data, second.data} == {b"bob-kp-1", b"bob-kp-2"}
    assert chat.unclaimed_count(db, b_dev.id) == 0
    with pytest.raises(Conflict, match="needs to open McXus"):
        chat.claim_key_package(db, alice, bob.id)


def test_cannot_claim_own_or_overfill(db, pair):
    _, bob, _, b_dev = pair
    with pytest.raises(AppError, match="yourself"):
        chat.claim_key_package(db, bob, bob.id)
    with pytest.raises(AppError, match="at most 100"):
        chat.upload_key_packages(db, bob, b_dev.id, [b64(b"x")] * 99)


def test_concurrent_claims_never_share_a_key_package(db, pair):
    alice, bob, _, _ = pair
    from app.db import get_sessionmaker

    got: list[bytes] = []
    barrier = threading.Barrier(2)

    def claim():
        with get_sessionmaker()() as session:
            barrier.wait()
            kp = chat.claim_key_package(session, session.get(type(alice), alice.id), bob.id)
            got.append(kp.data)
            session.commit()

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(got) == [b"bob-kp-1", b"bob-kp-2"]


def test_one_direct_chat_per_pair(db, pair):
    alice, bob, _, _ = pair
    c1 = chat.open_direct(db, alice, bob.id, None)
    c2 = chat.open_direct(db, bob, alice.id, None)
    db.commit()
    assert c1.id == c2.id
    with pytest.raises(AppError, match="yourself"):
        chat.open_direct(db, alice, alice.id, None)


def test_only_first_welcome_is_accepted(db, pair):
    alice, bob, a_dev, b_dev = pair
    conv = chat.open_direct(db, alice, bob.id, None)
    with pytest.raises(Conflict, match="not set up"):
        chat.post_message(db, alice, a_dev.id, conv.id, "application", b64(b"too early"))
    chat.post_welcome(db, alice, a_dev.id, conv.id, bob.id, b64(b"w1"))
    db.commit()
    with pytest.raises(Conflict, match="already set up"):
        chat.post_welcome(db, bob, b_dev.id, conv.id, alice.id, b64(b"w2"))
    db.rollback()


def test_sync_delivers_to_members_only(db, pair):
    alice, bob, a_dev, b_dev = pair
    conv = start_chat(db, alice, bob, a_dev)
    chat.post_message(db, alice, a_dev.id, conv.id, "application", b64(b"ciphertext-1"))
    chat.post_message(db, bob, b_dev.id, conv.id, "application", b64(b"ciphertext-2"))
    db.commit()
    bob_view = chat.sync(db, bob, 0, 100, 0)
    assert [m.kind for m in bob_view] == ["welcome", "application", "application"]
    alice_view = chat.sync(db, alice, 0, 100, 0)
    assert [m.kind for m in alice_view] == ["application", "application"]  # the Welcome is only for Bob
    assert chat.sync(db, alice, alice_view[0].id, 100, 0)[0].payload == b"ciphertext-2"
    stranger = make_user(db)
    assert chat.sync(db, stranger, 0, 100, 0) == []
    with pytest.raises(NotFound):
        chat.post_message(db, stranger, chat.register_device(db, stranger, "x").id, conv.id, "application", b64(b"hi"))


def test_long_poll_returns_as_soon_as_a_message_arrives(db, pair):
    alice, bob, a_dev, _ = pair
    conv = start_chat(db, alice, bob, a_dev)
    seen = chat.sync(db, bob, 0, 100, 0)
    cursor = seen[-1].id
    calls = []

    def fake_sleep(_):
        calls.append(1)
        if len(calls) == 2:  # a message arrives while Bob is waiting
            from app.db import get_sessionmaker

            with get_sessionmaker()() as other:
                chat.post_message(
                    other, other.get(type(alice), alice.id), a_dev.id, conv.id, "application", b64(b"late")
                )
                other.commit()

    got = chat.sync(db, bob, cursor, 100, 10, sleep=fake_sleep)
    assert [m.payload for m in got] == [b"late"] and len(calls) == 2


def test_messages_expire_after_30_days(db, pair, fake_clock):
    alice, bob, a_dev, _ = pair
    conv = start_chat(db, alice, bob, a_dev)
    chat.post_message(db, alice, a_dev.id, conv.id, "application", b64(b"old"))
    db.commit()
    fake_clock.advance(days=30, seconds=1)
    assert chat.sync(db, bob, 0, 100, 0) == []
    assert purge_messages() == 2  # welcome + message
    assert db.query(MlsMessage).count() == 0


def test_payload_rules(db, pair):
    alice, bob, a_dev, _ = pair
    conv = start_chat(db, alice, bob, a_dev)
    with pytest.raises(AppError, match="base64"):
        chat.post_message(db, alice, a_dev.id, conv.id, "application", "not base64!!")
    with pytest.raises(AppError, match="too large"):
        chat.post_message(db, alice, a_dev.id, conv.id, "application", b64(b"x" * (64 * 1024 + 1)))
    with pytest.raises(NotFound):
        chat.post_message(db, alice, chat.register_device(db, bob, "bob2").id, conv.id, "application", b64(b"x"))


def test_chat_over_http(client, db):
    seller, buyer = make_user(db, name="Kila"), make_user(db, tier=1, name="Ruth")
    h_s, h_b = auth(seller), auth(buyer)
    s_dev = client.post("/v1/devices", json={"name": "Seller phone"}, headers=h_s).json()["device_id"]
    b_dev = client.post("/v1/devices", json={}, headers=h_b).json()["device_id"]
    assert client.post("/v1/keys", json={"device_id": s_dev, "key_packages": [b64(b"kp")]}, headers=h_s).json() == {
        "unclaimed": 1
    }
    found = client.post("/v1/users/lookup", json={"phone": seller.phone}, headers=h_b).json()
    assert found["id"] == str(seller.id) and found["name"] == "Kila"
    conv = client.post("/v1/conversations", json={"peer_user_id": str(seller.id)}, headers=h_b).json()
    assert conv["encryption_ready"] is False and conv["peer"]["name"] == "Kila"
    kp = client.post("/v1/keys/claim", json={"user_id": str(seller.id)}, headers=h_b).json()
    assert base64.b64decode(kp["key_package"]) == b"kp"
    w = client.post(
        f"/v1/conversations/{conv['id']}/welcome",
        json={"device_id": b_dev, "recipient_user_id": str(seller.id), "payload": b64(b"welcome")},
        headers=h_b,
    )
    assert w.status_code == 201
    sent = client.post(
        f"/v1/conversations/{conv['id']}/messages",
        json={"device_id": b_dev, "payload": b64(b"encrypted hello")},
        headers=h_b,
    ).json()
    synced = client.get("/v1/messages/sync", params={"after": 0}, headers=h_s).json()
    assert [m["kind"] for m in synced] == ["welcome", "application"]
    assert base64.b64decode(synced[1]["payload"]) == b"encrypted hello" and synced[1]["id"] == sent["id"]
    convs = client.get("/v1/conversations", headers=h_s).json()
    assert len(convs) == 1 and convs[0]["encryption_ready"] is True and convs[0]["started_by_me"] is False


def test_expiry_setting(fake_clock, db, pair):
    alice, bob, a_dev, _ = pair
    conv = start_chat(db, alice, bob, a_dev)
    m = chat.post_message(db, alice, a_dev.id, conv.id, "application", b64(b"x"))
    assert m.expires_at - m.created_at == timedelta(days=30)


def test_new_device_retires_old_key_packages(db, pair):
    alice, bob, _, b_dev = pair
    assert chat.unclaimed_count(db, b_dev.id) == 2
    new_dev = chat.register_device(db, bob, "reinstalled")  # old keys were lost with the old install
    db.commit()
    assert chat.unclaimed_count(db, b_dev.id) == 0
    with pytest.raises(Conflict, match="needs to open McXus"):
        chat.claim_key_package(db, alice, bob.id)
    chat.upload_key_packages(db, bob, new_dev.id, [b64(b"fresh")])
    assert chat.claim_key_package(db, alice, bob.id).data == b"fresh"

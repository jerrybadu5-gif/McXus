"""M3.2: group chats (MLS commits accepted once per epoch), encrypted chat files, content-free pushes."""

import base64
import io
import json
import urllib.error

import pytest

from app import push
from app.config import get_settings
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.jobs import purge_messages
from app.messaging import service as chat
from app.models import Device, MediaBlob, MlsMessage
from tests.conftest import auth, make_user


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def phone(db, name, tier=0):
    user = make_user(db, tier=tier, name=name)
    device = chat.register_device(db, user, f"{name} phone")
    chat.upload_key_packages(db, user, device.id, [b64(f"{name}-kp-{i}".encode()) for i in range(3)])
    return user, device


@pytest.fixture
def church(db):
    admin, a_dev = phone(db, "Pastor")
    bob, b_dev = phone(db, "Bob")
    cara, c_dev = phone(db, "Cara")
    group = chat.create_group(db, admin, "Eriku Youth Group")
    db.commit()
    return admin, a_dev, bob, b_dev, cara, c_dev, group


def add(db, admin, a_dev, group, people, epoch):
    for p in people:
        chat.claim_key_package(db, admin, p.id, group.id)
    commit, welcomes = chat.add_members(
        db, admin, a_dev.id, group.id, [p.id for p in people], epoch, b64(b"commit-%d" % epoch), b64(b"welcome")
    )
    db.commit()
    return commit, welcomes


def kinds(db, user):
    return [(m.kind, m.epoch) for m in chat.sync(db, user, 0, 100, 0)]


def test_group_add_flow_and_epochs(db, church):
    admin, a_dev, bob, b_dev, cara, c_dev, group = church
    assert chat.group_members(db, admin, group.id)[0].role == "admin"
    commit, welcomes = add(db, admin, a_dev, group, [bob, cara], 0)
    assert commit.epoch == 0 and group.epoch == 1 and len(welcomes) == 2
    # Bob gets his own Welcome (before the commit), the commit and the notice; not Cara's Welcome.
    assert kinds(db, bob) == [("welcome", None), ("commit", 0), ("event", None)]
    event = chat.sync(db, bob, 0, 100, 0)[-1]
    assert json.loads(event.payload) == {"type": "added", "by": str(admin.id), "users": [str(bob.id), str(cara.id)]}
    # Messages reach every member.
    chat.post_message(db, cara, c_dev.id, group.id, "application", b64(b"Moning olgeta"))
    db.commit()
    assert [k for k, _ in kinds(db, bob)][-1] == "application"
    rows = {r["conversation"].id: r for r in chat.conversations_for(db, bob)}
    assert (
        rows[group.id]["member_count"] == 3 and rows[group.id]["role"] == "member" and rows[group.id]["peer_id"] is None
    )


def test_only_one_change_per_epoch(db, church):
    admin, a_dev, bob, _, cara, _, group = church
    add(db, admin, a_dev, group, [bob], 0)
    chat.set_role(db, admin, group.id, bob.id, "admin")
    db.commit()
    dan, _ = phone(db, "Dan")
    chat.claim_key_package(db, admin, cara.id, group.id)
    chat.claim_key_package(db, bob, dan.id, group.id)
    b_dev = db.query(Device).filter_by(user_id=bob.id).one()
    # Both admins made a change at epoch 1; the first one to arrive wins, the other must refresh and retry.
    chat.add_members(db, admin, a_dev.id, group.id, [cara.id], 1, b64(b"c-admin"), b64(b"w"))
    db.commit()
    with pytest.raises(Conflict, match="changed meanwhile"):
        chat.add_members(db, bob, b_dev.id, group.id, [dan.id], 1, b64(b"c-bob"), b64(b"w"))
    db.rollback()
    chat.add_members(db, bob, b_dev.id, group.id, [dan.id], 2, b64(b"c-bob"), b64(b"w"))
    db.commit()
    assert len(chat.group_members(db, admin, group.id)) == 4


def test_admin_rights(db, church):
    admin, a_dev, bob, b_dev, cara, _, group = church
    add(db, admin, a_dev, group, [bob], 0)
    with pytest.raises(Forbidden):
        chat.claim_key_package(db, bob, cara.id, group.id)
    with pytest.raises(Forbidden):
        chat.add_members(db, bob, b_dev.id, group.id, [cara.id], 1, b64(b"c"), b64(b"w"))
    db.rollback()
    with pytest.raises(Conflict, match="Already in the group"):
        chat.claim_key_package(db, admin, bob.id, group.id)
    with pytest.raises(AppError, match="Group Welcomes"):
        chat.post_welcome(db, admin, a_dev.id, group.id, bob.id, b64(b"w"))
    with pytest.raises(AppError, match="Only application"):
        chat.post_message(db, admin, a_dev.id, group.id, "commit", b64(b"c"))
    stranger, _ = phone(db, "Stranger")
    with pytest.raises(NotFound):
        chat.group_members(db, stranger, group.id)


def test_group_size_limit(db, church, monkeypatch):
    admin, a_dev, bob, _, cara, _, group = church
    monkeypatch.setattr(get_settings(), "max_group_members", 2)
    chat.claim_key_package(db, admin, bob.id, group.id)
    chat.claim_key_package(db, admin, cara.id, group.id)
    with pytest.raises(Conflict, match="at most 2"):
        chat.add_members(db, admin, a_dev.id, group.id, [bob.id, cara.id], 0, b64(b"c"), b64(b"w"))


def test_remove_and_leave(db, church):
    admin, a_dev, bob, b_dev, cara, c_dev, group = church
    add(db, admin, a_dev, group, [bob, cara], 0)
    chat.remove_members(db, admin, a_dev.id, group.id, [cara.id], 1, b64(b"remove-cara"))
    db.commit()
    seen_by_cara = len(chat.sync(db, cara, 0, 100, 0))
    chat.post_message(db, bob, b_dev.id, group.id, "application", b64(b"after Cara was removed"))
    db.commit()
    assert len(chat.sync(db, cara, 0, 100, 0)) == 0  # removed: sees nothing of the group any more
    assert seen_by_cara >= 0
    with pytest.raises(NotFound):
        chat.post_message(db, cara, c_dev.id, group.id, "application", b64(b"hello?"))
    db.rollback()
    # The only admin leaves: Bob becomes admin, and gets a notice so his phone removes the Pastor's keys.
    chat.leave_group(db, admin, group.id)
    db.commit()
    assert [(m.user_id, m.role) for m in chat.group_members(db, bob, group.id)] == [(bob.id, "admin")]
    notice = chat.sync(db, bob, 0, 100, 0)[-1]
    assert notice.kind == "event" and json.loads(notice.payload) == {"type": "left", "users": [str(admin.id)]}
    chat.remove_members(db, bob, b_dev.id, group.id, [admin.id], 2, b64(b"remove-pastor-keys"))
    db.commit()
    assert db.get(type(group), group.id).epoch == 3


def test_encrypted_files(db, church, tmp_path, monkeypatch, fake_clock):
    admin, a_dev, bob, _, cara, _, group = church
    monkeypatch.setattr(get_settings(), "blob_dir", str(tmp_path))
    add(db, admin, a_dev, group, [bob], 0)
    blob = chat.save_blob(db, admin, group.id, b"\x00encrypted-photo-bytes")
    db.commit()
    assert chat.read_blob(db, bob, blob.id) == b"\x00encrypted-photo-bytes"
    with pytest.raises(NotFound):
        chat.read_blob(db, cara, blob.id)  # not in the group
    with pytest.raises(AppError, match="too large"):
        chat.save_blob(db, admin, group.id, b"x" * (get_settings().max_blob_bytes + 1))
    fake_clock.advance(days=30, seconds=1)
    assert purge_messages() >= 1
    assert db.query(MediaBlob).count() == 0 and not any(tmp_path.rglob("*" + blob.id.hex))


def test_push_targets_skip_sender_and_strangers(db, church):
    admin, a_dev, bob, b_dev, cara, c_dev, group = church
    for user, device, token in ((admin, a_dev, "tok-admin"), (bob, b_dev, "tok-bob"), (cara, c_dev, "tok-cara")):
        chat.set_push_token(db, user, device.id, token)
    commit, welcomes = add(db, admin, a_dev, group, [bob], 0)
    assert chat.push_targets(db, welcomes[0]) == ["tok-bob"]  # a Welcome wakes only its recipient
    message = chat.post_message(db, bob, b_dev.id, group.id, "application", b64(b"hi"))
    assert chat.push_targets(db, message) == ["tok-admin"]  # not Bob's own phone, not Cara (not a member)


class FakeOpener:
    def __init__(self, fail_with: int | None = None):
        self.requests = []
        self.fail_with = fail_with

    def __call__(self, request, timeout):
        self.requests.append(request)
        if request.full_url.endswith("/token"):
            return io.BytesIO(json.dumps({"access_token": "ya29.test", "expires_in": 3600}).encode())
        if self.fail_with:
            raise urllib.error.HTTPError(request.full_url, self.fail_with, "x", {}, None)
        return io.BytesIO(b"{}")


def _fcm(opener):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    creds = {
        "project_id": "mcxus-test",
        "client_email": "push@mcxus-test.iam",
        "private_key": pem.decode(),
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return push.Fcm(creds, opener=opener)


def test_fcm_push_carries_no_content():
    opener = FakeOpener()
    assert _fcm(opener).send("device-token") is True
    sent = json.loads(opener.requests[-1].data)
    assert sent["message"]["data"] == {"t": "sync"} and "notification" not in sent["message"]
    assert opener.requests[-1].full_url.endswith("/projects/mcxus-test/messages:send")
    assert opener.requests[-1].headers["Authorization"] == "Bearer ya29.test"
    assert _fcm(FakeOpener(fail_with=404)).send("uninstalled") is False


def test_groups_over_http(client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "blob_dir", str(tmp_path))
    admin, bob = make_user(db, name="Pastor"), make_user(db, name="Bob")
    h_a, h_b = auth(admin), auth(bob)
    a_dev = client.post("/v1/devices", json={}, headers=h_a).json()["device_id"]
    b_dev = client.post("/v1/devices", json={}, headers=h_b).json()["device_id"]
    client.post("/v1/keys", json={"device_id": b_dev, "key_packages": [b64(b"bob-kp")]}, headers=h_b)
    group = client.post("/v1/groups", json={"title": "Eriku Youth"}, headers=h_a).json()
    assert group["kind"] == "group" and group["title"] == "Eriku Youth" and group["peer"] is None
    kp = client.post("/v1/keys/claim", json={"user_id": str(bob.id), "group_id": group["id"]}, headers=h_a)
    assert kp.status_code == 200
    body = {
        "device_id": a_dev,
        "user_ids": [str(bob.id)],
        "epoch": 0,
        "commit": b64(b"commit"),
        "welcome": b64(b"welc"),
    }
    r = client.post(f"/v1/groups/{group['id']}/members", json=body, headers=h_a)
    assert r.status_code == 200 and r.json()["epoch"] == 0
    again = client.post(f"/v1/groups/{group['id']}/members", json=body, headers=h_a)
    assert again.status_code == 400 and again.json()["error"]["code"] == "no_new_members"
    info = client.get(f"/v1/groups/{group['id']}", headers=h_b).json()
    assert info["epoch"] == 1 and [m["role"] for m in info["members"]] == ["admin", "member"]
    up = client.post(
        f"/v1/conversations/{group['id']}/blobs",
        content=b"\x01\x02cipher",
        headers={**h_a, "Content-Type": "application/octet-stream"},
    )
    assert up.status_code == 201 and up.json()["size"] == 8
    assert client.get(f"/v1/blobs/{up.json()['id']}", headers=h_b).content == b"\x01\x02cipher"
    assert client.post(f"/v1/devices/{b_dev}/push-token", json={"token": "fcm-bob"}, headers=h_b).status_code == 204
    assert db.get(Device, b_dev).push_token == "fcm-bob"
    convs = client.get("/v1/conversations", headers=h_b).json()
    assert convs[0]["kind"] == "group" and convs[0]["member_count"] == 2
    assert client.post(f"/v1/groups/{group['id']}/leave", headers=h_b).status_code == 204
    assert client.get("/v1/conversations", headers=h_b).json() == []
    assert db.query(MlsMessage).filter_by(kind="event").count() == 2


def test_one_device_per_account_holds_the_keys(db, church):
    admin, a_dev, bob, b_phone, cara, _, group = church
    # Bob opens McXus on a second device (the emulator): it becomes the device in use.
    b_emulator = chat.register_device(db, bob, "Emulator")
    chat.upload_key_packages(db, bob, b_emulator.id, [b64(b"emu-kp")])
    db.commit()
    kp = chat.claim_key_package(db, admin, bob.id, group.id)
    assert kp.device_id == b_emulator.id  # new chats are set up on the device in use
    chat.add_members(db, admin, a_dev.id, group.id, [bob.id], 0, b64(b"c"), b64(b"w"), {bob.id: kp.device_id})
    db.commit()
    # Only the emulator receives the Welcome; the phone is not asked to open something it cannot.
    assert [m.kind for m in chat.sync(db, bob, 0, 100, 0, device_id=b_emulator.id)][0] == "welcome"
    assert "welcome" not in [m.kind for m in chat.sync(db, bob, 0, 100, 0, device_id=b_phone.id)]
    rows = {r["conversation"].id: r for r in chat.conversations_for(db, bob)}
    assert rows[group.id]["key_device_id"] == b_emulator.id
    assert {r["conversation"].id: r for r in chat.conversations_for(db, admin)}[group.id]["key_device_id"] == a_dev.id
    # Back on the phone: it becomes active and the emulator's unused KeyPackages are retired.
    chat.upload_key_packages(db, bob, b_emulator.id, [b64(b"emu-kp-2")])
    chat.activate_device(db, bob, b_phone.id)
    db.commit()
    assert chat.unclaimed_count(db, b_emulator.id) == 0
    chat.upload_key_packages(db, bob, b_phone.id, [b64(b"phone-kp-new")])  # the app tops up after activating
    assert (
        chat.claim_key_package(db, cara, bob.id).device_id == b_phone.id
        if chat.open_direct(db, cara, bob.id, None)
        else False
    )
    with pytest.raises(AppError, match="does not belong"):
        chat.add_members(db, admin, a_dev.id, group.id, [cara.id], 1, b64(b"c"), b64(b"w"), {cara.id: b_phone.id})

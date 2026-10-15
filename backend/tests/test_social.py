"""M5: status (contacts, 24 h), posts with likes and comments, channels, reports and moderation."""

import io
import os

from PIL import Image

from app.messaging import service as chat
from app.models import Listing
from tests.conftest import auth, make_user


def jpeg() -> bytes:
    out = io.BytesIO()
    exif = Image.Exif()
    exif[0x8825] = {2: (9.0, 26.0, 0.0)}
    Image.new("RGB", (1600, 1200), (30, 80, 160)).save(out, format="JPEG", exif=exif)
    return out.getvalue()


def chatting(db, a, b):
    chat.open_direct(db, a, b.id, None)
    db.commit()


def test_status_is_for_contacts_only_and_disappears(client, db, users, fake_clock):
    ruth, kila, stranger = users["buyer"], users["seller"], make_user(db, name="stranger")
    chatting(db, ruth, kila)
    r = client.post("/v1/status", headers=auth(ruth), json={"text": "Market day tomorrow!", "color": "#134074"})
    assert r.status_code == 201
    photo = client.post(
        "/v1/status/photo", headers=auth(ruth), files={"file": ("a.jpg", jpeg())}, params={"caption": "Fresh kaukau"}
    )
    assert photo.status_code == 201
    photo_id = photo.json()["id"]

    board = client.get("/v1/status", headers=auth(kila)).json()
    assert [g["user"]["name"] for g in board["contacts"]] == ["buyer"] and board["contacts"][0]["all_seen"] is False
    assert len(board["contacts"][0]["items"]) == 2
    assert client.get("/v1/status", headers=auth(stranger)).json()["contacts"] == []
    assert client.get(f"/v1/status/{photo_id}/photo", headers=auth(stranger)).status_code == 404
    img = client.get(f"/v1/status/{photo_id}/photo", headers=auth(kila))
    with Image.open(io.BytesIO(img.content)) as im:
        assert 0x8825 not in im.getexif()

    client.post(f"/v1/status/{photo_id}/seen", headers=auth(kila))
    mine = client.get("/v1/status", headers=auth(ruth)).json()["mine"]
    assert [s["views"] for s in mine] == [0, 1]
    assert [v["user"]["name"] for v in client.get(f"/v1/status/{photo_id}/viewers", headers=auth(ruth)).json()] == [
        "seller"
    ]

    # Hide from Kila
    client.put("/v1/status/hidden", headers=auth(ruth), json={"user_ids": [str(kila.id)]})
    assert client.get("/v1/status", headers=auth(kila)).json()["contacts"] == []
    client.put("/v1/status/hidden", headers=auth(ruth), json={"user_ids": []})

    # After 24 hours: gone, and the photo file is deleted by the worker
    from app.jobs import purge_messages

    files = [os.path.join(d, f) for d, _, fs in os.walk(os.environ["MCXUS_STATUS_DIR"]) for f in fs]
    assert files
    fake_clock.advance(hours=24, seconds=1)
    assert client.get("/v1/status", headers=auth(kila)).json()["contacts"] == []
    assert purge_messages() >= 2
    assert not any(os.path.exists(f) for f in files)


def test_posts_feed_likes_comments(client, db, users, fake_clock):
    ruth, kila, other = users["buyer"], users["seller"], make_user(db, name="other")
    chatting(db, ruth, kila)
    public = client.post(
        "/v1/posts",
        headers=auth(ruth),
        data={"text": "Moning PNG!"},
        files=[("files", ("a.jpg", jpeg())), ("files", ("b.jpg", jpeg()))],
    )
    assert public.status_code == 201, public.text
    assert len(public.json()["photos"]) == 2 and public.json()["photos"][0]["width"] == 1280
    fake_clock.advance(minutes=1)
    private = client.post("/v1/posts", headers=auth(ruth), data={"text": "Only for friends", "visibility": "contacts"})
    assert private.status_code == 201

    def feed_texts(user):
        return [
            i["post"]["text"] for i in client.get("/v1/feed", headers=auth(user)).json()["items"] if i["type"] == "post"
        ]

    assert feed_texts(kila) == ["Only for friends", "Moning PNG!"]
    assert feed_texts(other) == ["Moning PNG!"]
    assert client.get(f"/v1/posts/{private.json()['id']}", headers=auth(other)).status_code == 404

    pid = public.json()["id"]
    assert client.post(f"/v1/posts/{pid}/like", headers=auth(kila)).json()["likes"] == 1
    assert client.post(f"/v1/posts/{pid}/like", headers=auth(kila)).json()["likes"] == 1  # once per person
    assert client.post(f"/v1/posts/{pid}/like", headers=auth(other)).json()["liked"] is True
    assert client.delete(f"/v1/posts/{pid}/like", headers=auth(other)).json()["likes"] == 1

    comments = client.post(f"/v1/posts/{pid}/comments", headers=auth(other), json={"text": "Moning!"}).json()
    assert [c["text"] for c in comments] == ["Moning!"]
    assert client.get(f"/v1/posts/{pid}", headers=auth(kila)).json()["comments"] == 1
    # The post's author may delete any comment on it
    assert client.delete(f"/v1/comments/{comments[0]['id']}", headers=auth(ruth)).status_code == 204
    assert client.get(f"/v1/posts/{pid}", headers=auth(kila)).json()["comments"] == 0

    # Level 0 accounts can't post on Discover; nobody else can delete my post
    newbie = make_user(db, tier=0)
    assert client.post("/v1/posts", headers=auth(newbie), data={"text": "hi"}).json()["error"]["code"] == "kyc_required"
    assert client.delete(f"/v1/posts/{pid}", headers=auth(kila)).status_code == 403


def test_feed_mixes_new_listings(client, db, users):
    client.post("/v1/posts", headers=auth(users["buyer"]), data={"text": "First post"})
    db.add(
        Listing(
            seller_id=users["seller"].id,
            title="Bilum",
            description="",
            category_id=_leaf(db),
            price=50,
            quantity_available=1,
            condition="new",
            province_id=_province(db),
            delivery_options=["meetup"],
        )
    )
    db.commit()
    kinds = [i["type"] for i in client.get("/v1/feed", headers=auth(users["buyer"])).json()["items"]]
    assert sorted(kinds) == ["listing", "post"]
    only_posts = client.get("/v1/feed", headers=auth(users["buyer"]), params={"listings": "false"}).json()["items"]
    assert [i["type"] for i in only_posts] == ["post"]


def _leaf(db):
    from sqlalchemy import select

    from app.models import Category

    return db.scalars(select(Category.id).where(Category.parent_id.is_not(None))).first()


def _province(db):
    from sqlalchemy import select

    from app.models import Location

    return db.scalars(select(Location.id).where(Location.parent_id.is_(None))).first()


def test_channels(client, db, users):
    owner, admin, fan = users["seller"], users["buyer"], make_user(db, name="fan")
    basic = make_user(db, tier=1)
    assert client.post("/v1/channels", headers=auth(basic), json={"name": "Mine", "handle": "mine"}).status_code == 403
    assert (
        client.post("/v1/channels", headers=auth(owner), json={"name": "Xx", "handle": "Bad Handle!"}).json()["error"][
            "code"
        ]
        == "handle_invalid"
    )
    ch = client.post(
        "/v1/channels",
        headers=auth(owner),
        json={"name": "Eriku Youth", "handle": "@Eriku-Youth", "description": "News for the youth group"},
    ).json()
    assert ch["handle"] == "eriku-youth" and ch["role"] == "owner" and ch["followers"] == 1
    assert (
        client.post("/v1/channels", headers=auth(owner), json={"name": "Again", "handle": "eriku-youth"}).json()[
            "error"
        ]["code"]
        == "handle_taken"
    )
    cid = ch["id"]

    assert client.post("/v1/posts", headers=auth(admin), data={"text": "x", "channel_id": cid}).status_code == 403
    client.post(f"/v1/channels/{cid}/admins", headers=auth(owner), json={"user_id": str(admin.id)})
    assert (
        client.post(
            "/v1/posts", headers=auth(admin), data={"text": "Meeting Saturday 3pm", "channel_id": cid}
        ).status_code
        == 201
    )

    assert [c["handle"] for c in client.get("/v1/channels", headers=auth(fan), params={"q": "YOUTH eriku"}).json()] == [
        "eriku-youth"
    ]
    feed = [
        i["post"]["text"]
        for i in client.get("/v1/feed", headers=auth(fan), params={"listings": "false"}).json()["items"]
    ]
    assert feed == []  # channel posts reach the feed of followers
    assert client.post(f"/v1/channels/{cid}/follow", headers=auth(fan)).json()["followers"] == 2
    feed = [i["post"] for i in client.get("/v1/feed", headers=auth(fan), params={"listings": "false"}).json()["items"]]
    assert [(p["text"], p["channel"]["handle"]) for p in feed] == [("Meeting Saturday 3pm", "eriku-youth")]
    assert [c["name"] for c in client.get("/v1/channels/mine", headers=auth(fan)).json()] == ["Eriku Youth"]
    assert client.delete(f"/v1/channels/{cid}/follow", headers=auth(owner)).json()["error"]["code"] == "owner_follows"
    assert client.delete(f"/v1/channels/{cid}/follow", headers=auth(fan)).json()["followers"] == 1


def test_reports_hide_until_a_moderator_decides(client, db, users):
    author = users["buyer"]
    mod = make_user(db, role="moderator", name="mod")
    pid = client.post("/v1/posts", headers=auth(author), data={"text": "Buy crypto, 300% return!"}).json()["id"]
    reporters = [make_user(db, name=f"r{i}") for i in range(3)]
    for r in reporters[:2]:
        assert (
            client.post(
                "/v1/reports", headers=auth(r), json={"target_type": "post", "target_id": pid, "reason": "scam"}
            ).status_code
            == 201
        )
    assert (
        client.post(
            "/v1/reports", headers=auth(reporters[0]), json={"target_type": "post", "target_id": pid, "reason": "scam"}
        ).json()["error"]["code"]
        == "already_reported"
    )
    assert client.get(f"/v1/posts/{pid}", headers=auth(users["seller"])).status_code == 200
    client.post(
        "/v1/reports",
        headers=auth(reporters[2]),
        json={"target_type": "post", "target_id": pid, "reason": "scam", "note": "fake investment"},
    )
    assert client.get(f"/v1/posts/{pid}", headers=auth(users["seller"])).status_code == 404  # hidden after 3 reports
    assert client.get(f"/v1/posts/{pid}", headers=auth(author)).json()["status"] == "under_review"

    queue = client.get("/v1/mod/content-reports", headers=auth(mod)).json()
    assert [(q["target_type"], q["reports"], q["reasons"], q["notes"]) for q in queue] == [
        ("post", 3, ["scam"], ["fake investment"])
    ]
    assert queue[0]["content"]["text"] == "Buy crypto, 300% return!"
    assert client.get("/v1/admin/overview", headers=auth(mod)).json()["content_reports_open"] == 1
    client.post(f"/v1/mod/content/post/{pid}/decision", headers=auth(mod), json={"action": "remove"})
    assert client.get(f"/v1/posts/{pid}", headers=auth(author)).json()["status"] == "removed"
    assert client.get("/v1/mod/content-reports", headers=auth(mod)).json() == []

    # A channel can be reported and suspended; its posts disappear from everyone's feed.
    ch = client.post("/v1/channels", headers=auth(users["seller"]), json={"name": "Deals", "handle": "deals"}).json()
    client.post("/v1/posts", headers=auth(users["seller"]), data={"text": "Cheap phones", "channel_id": ch["id"]})
    client.post(f"/v1/channels/{ch['id']}/follow", headers=auth(author))
    client.post(
        "/v1/reports", headers=auth(author), json={"target_type": "channel", "target_id": ch["id"], "reason": "scam"}
    )
    client.post(f"/v1/mod/content/channel/{ch['id']}/decision", headers=auth(mod), json={"action": "remove"})
    assert client.get(f"/v1/channels/{ch['id']}", headers=auth(author)).status_code == 404
    feed = client.get("/v1/feed", headers=auth(author), params={"listings": "false"}).json()["items"]
    assert [i["post"]["text"] for i in feed] == ["Buy crypto, 300% return!"]  # only my own (removed) post
    actions = [e["action"] for e in client.get("/v1/admin/audit", headers=auth(make_user(db, role="admin"))).json()]
    assert actions[:2] == ["channel_remove", "post_remove"]

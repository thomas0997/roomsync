"""Inbox: private messages between room-mates. Every security rule from the contract is tested here."""
import pytest

from app import ratelimit
from app.db import SessionLocal
from app.models import InboxMessage, User, utcnow

from .conftest import join_room, make_room, signup


def _setup(client):
    """Alice and Bob share a room. Carol is in another room (a stranger to them). Dave has no room."""
    alice = signup(client, "a@example.com", "Alice")
    bob = signup(client, "b@example.com", "Bob")
    carol = signup(client, "c@example.com", "Carol")
    signup(client, "d@example.com", "Dave")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    make_room(client, carol, "Other room")
    return alice, bob, carol


EMAIL_IDS = {"a@example.com": "Alice", "b@example.com": "Bob", "c@example.com": "Carol", "d@example.com": "Dave"}


def _id_of(email):
    with SessionLocal() as db:
        return db.query(User.id).filter(User.email == email).scalar()


def _send(client, headers, to="b@example.com", subject="Hello", body="Hi there"):
    """`to` is an email only to find the person's id in the test database; the API takes the id."""
    to_id = to if isinstance(to, int) else (_id_of(to) or 999999)
    return client.post("/inbox", json={"to_user_id": to_id, "subject": subject, "body": body}, headers=headers)


def _uid(client, headers):
    return client.get("/users/me", headers=headers).json()["id"]


# ---------- sending ----------

def test_send_and_receive(client):
    alice, bob, _ = _setup(client)
    r = _send(client, alice)
    assert r.status_code == 201, r.text
    m = r.json()
    assert (m["from_name"], m["to_name"], m["subject"], m["body"]) == ("Alice", "Bob", "Hello", "Hi there")
    assert m["read_at"] is None and m["archived"] is False and m["reply_to_id"] is None
    inbox = client.get("/inbox", headers=bob).json()
    assert [x["id"] for x in inbox] == [m["id"]]
    assert client.get("/inbox?folder=sent", headers=alice).json()[0]["id"] == m["id"]
    assert client.get("/inbox", headers=alice).json() == []  # the sender's inbox is empty


def test_no_email_address_is_ever_returned(client):
    alice, bob, _ = _setup(client)
    _send(client, alice)
    for headers in (alice, bob):
        for folder in ("inbox", "sent"):
            assert "@example.com" not in client.get(f"/inbox?folder={folder}", headers=headers).text


def test_syncmates_lists_only_room_mates_with_names_and_rooms(client):
    alice, bob, carol = _setup(client)
    r = client.get("/inbox/syncmates", headers=alice)
    assert r.status_code == 200
    assert r.json() == [{"user_id": _id_of("b@example.com"), "name": "Bob", "rooms": [client.get("/rooms", headers=alice).json()[0]["name"]]}]
    assert "@example.com" not in r.text
    assert client.get("/inbox/syncmates", headers=carol).json() == []  # alone in her room
    assert client.get("/inbox/syncmates").status_code == 401


def test_syncmates_hides_deleted_accounts(client):
    alice, _, _ = _setup(client)
    with SessionLocal() as db:
        db.query(User).filter(User.email == "b@example.com").update({"deleted_at": utcnow()})
        db.commit()
    assert client.get("/inbox/syncmates", headers=alice).json() == []


def test_needs_login(client):
    assert client.get("/inbox").status_code == 401
    assert client.post("/inbox", json={}).status_code == 401
    assert client.get("/inbox/syncmates").status_code == 401
    assert client.get("/inbox/unread-count").status_code == 401
    assert client.get("/inbox/1").status_code == 401
    assert client.delete("/inbox/1").status_code == 401
    assert client.put("/inbox/blocks/1").status_code == 401


def test_unknown_id_stranger_and_deleted_account_look_identical(client):
    alice, bob, carol = _setup(client)
    unknown = _send(client, alice, to=987654)
    stranger = _send(client, alice, to="c@example.com")  # exists, but shares no room with Alice
    no_room = _send(client, alice, to="d@example.com")
    with SessionLocal() as db:  # a deleted account
        db.query(User).filter(User.email == "b@example.com").update({"deleted_at": utcnow()})
        db.commit()
    deleted = _send(client, alice, to="b@example.com")
    for r in (unknown, stranger, no_room, deleted):
        assert r.status_code == 404
        assert r.json() == {"detail": "Syncmate not found"}


def test_cannot_write_to_yourself(client):
    alice, _, _ = _setup(client)
    assert _send(client, alice, to="a@example.com").status_code == 422


def test_email_field_is_no_longer_accepted(client):
    alice, _, _ = _setup(client)
    r = client.post("/inbox", json={"to_email": "b@example.com", "subject": "s", "body": "x"}, headers=alice)
    assert r.status_code == 422


@pytest.mark.parametrize("payload", [
    {"to_user_id": 2, "subject": "", "body": "x"},
    {"to_user_id": 2, "subject": "   ", "body": "x"},
    {"to_user_id": 2, "subject": "s", "body": ""},
    {"to_user_id": 2, "subject": "s", "body": "   \n "},
    {"to_user_id": 2, "subject": "s" * 121, "body": "x"},
    {"to_user_id": 2, "subject": "s", "body": "x" * 2001},
    {"to_user_id": 0, "subject": "s", "body": "x"},
    {"to_user_id": "bob", "subject": "s", "body": "x"},
    {"to_user_id": 2, "subject": "s"},
    {"to_user_id": 2, "subject": "s", "body": "x", "from_user_id": 5},  # unknown fields are refused
])
def test_bad_input_is_422(client, payload):
    alice, _, _ = _setup(client)
    assert client.post("/inbox", json=payload, headers=alice).status_code == 422


def test_limits_at_the_edge_are_accepted_and_text_is_trimmed(client):
    alice, bob, _ = _setup(client)
    r = _send(client, alice, subject="  " + "s" * 120 + "  ", body="b" * 2000)
    assert r.status_code == 201
    assert r.json()["subject"] == "s" * 120 and len(r.json()["body"]) == 2000


def test_html_and_links_are_stored_as_plain_text_unchanged(client):
    alice, bob, _ = _setup(client)
    text = '<script>alert(1)</script> https://evil.example/x <b>hi</b>'
    _send(client, alice, subject="<img src=x>", body=text)
    got = client.get("/inbox", headers=bob).json()[0]
    assert got["body"] == text and got["subject"] == "<img src=x>"  # the page shows it with textContent


# ---------- reading, privacy ----------

def test_opening_marks_read_only_for_the_recipient_and_unread_count_follows(client):
    alice, bob, _ = _setup(client)
    mid = _send(client, alice).json()["id"]
    assert client.get("/inbox/unread-count", headers=bob).json() == {"count": 1}
    assert client.get("/inbox/unread-count", headers=alice).json() == {"count": 0}
    assert client.get(f"/inbox/{mid}", headers=alice).json()["read_at"] is None  # the sender looking does not count
    assert client.get("/inbox/unread-count", headers=bob).json() == {"count": 1}
    assert client.get(f"/inbox/{mid}", headers=bob).json()["read_at"] is not None
    assert client.get("/inbox/unread-count", headers=bob).json() == {"count": 0}


def test_a_third_person_and_a_missing_id_get_the_same_404(client):
    alice, bob, carol = _setup(client)
    mid = _send(client, alice).json()["id"]
    for call in (
        lambda h, i: client.get(f"/inbox/{i}", headers=h),
        lambda h, i: client.patch(f"/inbox/{i}", json={"archived": True}, headers=h),
        lambda h, i: client.delete(f"/inbox/{i}", headers=h),
        lambda h, i: client.post(f"/inbox/{i}/reply", json={"body": "x"}, headers=h),
    ):
        stranger = call(carol, mid)
        missing = call(carol, 99999)
        assert stranger.status_code == missing.status_code == 404
        assert stranger.json() == missing.json()
    assert client.get("/inbox", headers=carol).json() == []
    # and nothing changed for the real people
    assert client.get(f"/inbox/{mid}", headers=bob).status_code == 200


def test_admins_get_no_extra_access(client):
    alice, bob, _ = _setup(client)  # Alice is the room's admin
    carol_like = signup(client, "e@example.com", "Eve")
    code = client.get("/rooms", headers=alice).json()[0]["invite_code"]
    join_room(client, carol_like, code)
    mid = _send(client, bob, to="e@example.com").json()["id"]  # Bob to Eve; Alice is admin of their shared room
    assert client.get(f"/inbox/{mid}", headers=alice).status_code == 404
    assert client.get("/inbox", headers=alice).json() == []


# ---------- reply ----------

def test_reply_goes_to_the_other_person_with_re_subject(client):
    alice, bob, _ = _setup(client)
    mid = _send(client, alice, subject="Quiz?").json()["id"]
    r = client.post(f"/inbox/{mid}/reply", json={"body": "Yes, Friday"}, headers=bob)
    assert r.status_code == 201, r.text
    m = r.json()
    assert (m["subject"], m["reply_to_id"], m["to_name"], m["from_name"]) == ("Re: Quiz?", mid, "Alice", "Bob")
    assert client.get("/inbox", headers=alice).json()[0]["id"] == m["id"]
    again = client.post(f"/inbox/{m['id']}/reply", json={"body": "ok"}, headers=alice).json()
    assert again["subject"] == "Re: Quiz?"  # no "Re: Re:"


def test_sender_can_also_reply_to_their_own_message_goes_to_recipient(client):
    alice, bob, _ = _setup(client)
    mid = _send(client, alice).json()["id"]
    r = client.post(f"/inbox/{mid}/reply", json={"body": "one more thing"}, headers=alice)
    assert r.status_code == 201 and r.json()["to_name"] == "Bob"


def test_reply_validation(client):
    alice, bob, _ = _setup(client)
    mid = _send(client, alice).json()["id"]
    for payload in ({"body": ""}, {"body": "  "}, {"body": "x" * 2001}, {}, {"body": "x", "subject": "y"}):
        assert client.post(f"/inbox/{mid}/reply", json=payload, headers=bob).status_code == 422


def test_reply_fails_when_you_no_longer_share_a_room(client):
    alice, bob, _ = _setup(client)
    mid = _send(client, alice).json()["id"]
    room = client.get("/rooms", headers=bob).json()[0]
    bob_id = _uid(client, bob)
    assert client.delete(f"/rooms/{room['id']}/members/{bob_id}", headers=alice).status_code == 204
    r = client.post(f"/inbox/{mid}/reply", json={"body": "hi"}, headers=bob)
    assert r.status_code == 404 and r.json() == {"detail": "Syncmate not found"}


# ---------- folders, paging, archive, delete ----------

def test_list_validation_and_paging(client):
    alice, bob, _ = _setup(client)
    ids = [_send(client, alice, subject=f"m{i}").json()["id"] for i in range(5)]
    assert [m["id"] for m in client.get("/inbox?limit=2", headers=bob).json()] == [ids[4], ids[3]]
    page2 = client.get(f"/inbox?limit=2&before_id={ids[3]}", headers=bob).json()
    assert [m["id"] for m in page2] == [ids[2], ids[1]]
    for bad in ("folder=trash", "limit=0", "limit=101", "limit=abc", "before_id=0", "before_id=x"):
        assert client.get(f"/inbox?{bad}", headers=bob).status_code == 422


def test_archive_and_unarchive_by_recipient_only(client):
    alice, bob, _ = _setup(client)
    mid = _send(client, alice).json()["id"]
    assert client.patch(f"/inbox/{mid}", json={"archived": True}, headers=alice).status_code == 404  # sender cannot
    r = client.patch(f"/inbox/{mid}", json={"archived": True}, headers=bob)
    assert r.status_code == 200 and r.json()["archived"] is True
    assert client.get("/inbox", headers=bob).json() == []
    assert [m["id"] for m in client.get("/inbox?folder=archived", headers=bob).json()] == [mid]
    assert client.get("/inbox/unread-count", headers=bob).json() == {"count": 0}  # archived does not count as unread
    assert client.patch(f"/inbox/{mid}", json={"archived": False}, headers=bob).json()["archived"] is False
    assert client.patch(f"/inbox/{mid}", json={}, headers=bob).status_code == 422
    assert client.patch(f"/inbox/{mid}", json={"archived": "maybe"}, headers=bob).status_code == 422


def test_delete_only_removes_my_copy_until_both_remove_it(client):
    alice, bob, _ = _setup(client)
    mid = _send(client, alice).json()["id"]
    assert client.delete(f"/inbox/{mid}", headers=bob).status_code == 204
    assert client.get("/inbox", headers=bob).json() == []
    assert client.get(f"/inbox/{mid}", headers=bob).status_code == 404
    assert client.get(f"/inbox/{mid}", headers=alice).status_code == 200  # Alice keeps hers
    with SessionLocal() as db:
        assert db.get(InboxMessage, mid) is not None
    assert client.delete(f"/inbox/{mid}", headers=alice).status_code == 204
    with SessionLocal() as db:
        assert db.get(InboxMessage, mid) is None  # both removed: gone for good
    assert client.delete(f"/inbox/{mid}", headers=alice).status_code == 404


def test_deleting_the_original_keeps_the_reply(client):
    alice, bob, _ = _setup(client)
    mid = _send(client, alice).json()["id"]
    rid = client.post(f"/inbox/{mid}/reply", json={"body": "hi"}, headers=bob).json()["id"]
    client.delete(f"/inbox/{mid}", headers=alice)
    client.delete(f"/inbox/{mid}", headers=bob)
    got = client.get(f"/inbox/{rid}", headers=alice).json()
    assert got["reply_to_id"] is None


def test_deleted_account_shows_as_deleted_user(client):
    alice, bob, _ = _setup(client)
    mid = _send(client, alice).json()["id"]
    with SessionLocal() as db:
        db.query(User).filter(User.email == "a@example.com").update({"deleted_at": utcnow()})
        db.commit()
    got = client.get(f"/inbox/{mid}", headers=bob).json()
    assert got["from_name"] == "Deleted user"


# ---------- blocks ----------

def test_blocked_sender_gets_201_but_the_recipient_never_sees_it(client):
    alice, bob, _ = _setup(client)
    alice_id = _uid(client, alice)
    assert client.put(f"/inbox/blocks/{alice_id}", headers=bob).status_code == 204
    assert client.put(f"/inbox/blocks/{alice_id}", headers=bob).status_code == 204  # twice is fine
    r = _send(client, alice)
    assert r.status_code == 201  # Alice is not told
    mid = r.json()["id"]
    assert client.get("/inbox", headers=bob).json() == []
    assert client.get("/inbox/unread-count", headers=bob).json() == {"count": 0}
    assert client.get(f"/inbox/{mid}", headers=bob).status_code == 404
    assert [m["id"] for m in client.get("/inbox?folder=sent", headers=alice).json()] == [mid]  # looks normal to her
    # unblock: messages flow again
    assert client.delete(f"/inbox/blocks/{alice_id}", headers=bob).status_code == 204
    assert client.delete(f"/inbox/blocks/{alice_id}", headers=bob).status_code == 204
    _send(client, alice, subject="again")
    assert [m["subject"] for m in client.get("/inbox", headers=bob).json()] == ["again"]


def test_block_does_not_remove_old_messages_and_replies_are_blocked_too(client):
    alice, bob, _ = _setup(client)
    alice_id, bob_id = _uid(client, alice), _uid(client, bob)
    old = _send(client, alice).json()["id"]
    client.put(f"/inbox/blocks/{alice_id}", headers=bob)
    assert client.get(f"/inbox/{old}", headers=bob).status_code == 200
    client.post(f"/inbox/{old}/reply", json={"body": "still here"}, headers=alice)
    assert len(client.get("/inbox", headers=bob).json()) == 1  # only the old one
    assert client.get("/inbox?folder=sent", headers=alice).json()[0]["body"] == "still here"
    assert bob_id != alice_id


def test_block_target_rules(client):
    alice, bob, carol = _setup(client)
    assert client.put(f"/inbox/blocks/{_uid(client, alice)}", headers=alice).status_code == 404  # not yourself
    assert client.put("/inbox/blocks/99999", headers=alice).status_code == 404  # no such user
    # Carol shares no room with Alice and has not written to her: same 404 as a missing user
    assert client.put(f"/inbox/blocks/{_uid(client, carol)}", headers=alice).status_code == 404


# ---------- rate limits ----------

@pytest.fixture()
def limiter(monkeypatch):
    """Call limiter() AFTER the setup (signups have their own limits)."""
    def turn_on():
        monkeypatch.setattr(ratelimit, "ENABLED", True)
        ratelimit.reset()
    yield turn_on
    ratelimit.reset()


def test_ten_an_hour_to_the_same_person(client, limiter):
    alice, bob, _ = _setup(client)
    limiter()
    for _i in range(10):
        assert _send(client, alice).status_code == 201
    r = _send(client, alice)
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_twenty_an_hour_overall(client, limiter):
    alice, _, _ = _setup(client)
    code = client.get("/rooms", headers=alice).json()[0]["invite_code"]
    emails = []
    for i in range(5):  # five room-mates, so the per-person limit (10) is not what stops us
        signup_headers = signup(client, f"p{i}@example.com", f"P{i}")
        join_room(client, signup_headers, code)
        emails.append(f"p{i}@example.com")
    limiter()
    codes = [_send(client, alice, to=emails[i % 5]).status_code for i in range(21)]
    assert codes[:20] == [201] * 20 and codes[20] == 429


def test_replies_share_the_same_limits(client, limiter):
    alice, bob, _ = _setup(client)
    limiter()
    first = _send(client, alice).json()["id"]
    for _i in range(9):
        assert client.post(f"/inbox/{first}/reply", json={"body": "x"}, headers=alice).status_code == 201
    assert client.post(f"/inbox/{first}/reply", json={"body": "x"}, headers=alice).status_code == 429

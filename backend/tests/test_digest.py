"""Deadline reminder digest (app/digest.py): one email per eligible user per day, and the
GET /unsubscribe link it carries."""
from datetime import datetime, timedelta, timezone

import pytest

from app import mailer
from app.db import SessionLocal
from app.digest import run_digest, unsubscribe_token, verify_unsubscribe_token
from app.models import User, UserSettings
from tests.conftest import make_room, signup

SENT = []


@pytest.fixture(autouse=True)
def capture_mail(monkeypatch):
    SENT.clear()
    monkeypatch.setattr(mailer, "deliver", lambda **kw: SENT.append(kw) or True)


def verify(client, user_id: int):
    """Marks a user verified directly in the DB -- quicker than round-tripping a real email."""
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).update({"email_verified": True})
        db.commit()


def user_id_from(headers) -> int:
    import jwt
    token = headers["Authorization"].split(" ", 1)[1]
    return int(jwt.decode(token, options={"verify_signature": False})["sub"])


def due_soon(days=1):
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_task(client, headers, rid, due=None, title="Quiz 1"):
    r = client.post(
        f"/rooms/{rid}/tasks",
        json={"title": title, "type": "quiz", "due_at": due or due_soon()},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_unverified_user_gets_nothing(client):
    alice = signup(client)
    SENT.clear()  # signup's own verification email isn't what this test is about
    room = make_room(client, alice)
    make_task(client, alice, room["id"])
    with SessionLocal() as db:
        stats = run_digest(db)
    assert stats == {"eligible": 0, "emailed": 0, "skipped_nothing_due": 0}
    assert SENT == []


def test_verified_opted_in_user_with_a_due_soon_task_gets_emailed(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    room = make_room(client, alice)
    make_task(client, alice, room["id"])
    with SessionLocal() as db:
        stats = run_digest(db)
    assert stats == {"eligible": 1, "emailed": 1, "skipped_nothing_due": 0}
    assert len(SENT) == 1 and SENT[0]["to"] == "a@example.com" and SENT[0]["kind"] == "deadline_digest"
    assert "Quiz 1" in SENT[0]["text"] and "/unsubscribe?token=" in SENT[0]["text"]


def test_verified_user_with_nothing_due_soon_is_not_emailed(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    make_room(client, alice)  # a room but no tasks
    with SessionLocal() as db:
        stats = run_digest(db)
    assert stats == {"eligible": 1, "emailed": 0, "skipped_nothing_due": 1}
    assert SENT == []


def test_task_more_than_3_days_out_is_not_included(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    room = make_room(client, alice)
    make_task(client, alice, room["id"], due=due_soon(days=10))
    with SessionLocal() as db:
        stats = run_digest(db)
    assert stats["emailed"] == 0 and SENT == []


def test_overdue_task_is_not_included(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    room = make_room(client, alice)
    make_task(client, alice, room["id"], due="2020-01-01T00:00:00Z")  # long past
    with SessionLocal() as db:
        stats = run_digest(db)
    assert stats["emailed"] == 0 and SENT == []


def test_task_the_user_marked_done_is_excluded(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    room = make_room(client, alice)
    task = make_task(client, alice, room["id"])
    assert client.put(f"/tasks/{task['id']}/done", headers=alice).status_code == 200
    with SessionLocal() as db:
        stats = run_digest(db)
    assert stats["emailed"] == 0 and SENT == []


def test_opted_out_user_gets_nothing(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    room = make_room(client, alice)
    make_task(client, alice, room["id"])
    client.put("/users/me/settings", json={"notify_deadline_reminders": False}, headers=alice)
    with SessionLocal() as db:
        stats = run_digest(db)
    assert stats["eligible"] == 0 and SENT == []


def test_dry_run_sends_nothing_and_does_not_mark_sent(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    room = make_room(client, alice)
    make_task(client, alice, room["id"])
    with SessionLocal() as db:
        stats = run_digest(db, dry_run=True)
    assert stats["emailed"] == 1 and SENT == []  # counted, but nothing actually sent
    with SessionLocal() as db:
        assert db.get(User, uid).last_digest_sent_at is None


def test_second_run_the_same_day_does_not_double_send(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    room = make_room(client, alice)
    make_task(client, alice, room["id"])
    with SessionLocal() as db:
        run_digest(db)
    assert len(SENT) == 1
    with SessionLocal() as db:
        stats = run_digest(db)  # same calendar day: nobody is eligible again
    assert stats == {"eligible": 0, "emailed": 0, "skipped_nothing_due": 0}
    assert len(SENT) == 1


def test_a_new_day_sends_again(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    room = make_room(client, alice)
    now = datetime.now(timezone.utc)
    make_task(client, alice, room["id"], due=due_soon(days=2))  # safely inside both days' 3-day windows
    with SessionLocal() as db:
        run_digest(db, now=now)
    with SessionLocal() as db:
        stats = run_digest(db, now=now + timedelta(days=1))
    assert stats["emailed"] == 1
    assert len(SENT) == 2


def test_deleted_account_is_never_eligible(client):
    alice = signup(client)
    uid = user_id_from(alice)
    verify(client, uid)
    SENT.clear()  # signup's own verification email isn't what these tests are about
    room = make_room(client, alice)
    make_task(client, alice, room["id"])
    with SessionLocal() as db:
        db.query(User).filter(User.id == uid).update({"deleted_at": datetime.now(timezone.utc)})
        db.commit()
        stats = run_digest(db)
    assert stats["eligible"] == 0 and SENT == []


def test_unsubscribe_token_round_trips_and_rejects_tampering(client):
    token = unsubscribe_token(42)
    assert verify_unsubscribe_token(token) == 42
    assert verify_unsubscribe_token(token + "x") is None
    assert verify_unsubscribe_token("not-a-token") is None
    assert verify_unsubscribe_token("abc.def") is None  # non-numeric id


def test_unsubscribe_endpoint_turns_the_setting_off_without_login(client):
    alice = signup(client)
    uid = user_id_from(alice)
    token = unsubscribe_token(uid)
    r = client.get(f"/unsubscribe?token={token}")
    assert r.status_code == 200 and "unsubscribed" in r.text.lower()
    assert client.get("/users/me/settings", headers=alice).json()["notify_deadline_reminders"] is False


def test_unsubscribe_with_a_bad_token_is_400_and_changes_nothing(client):
    alice = signup(client)
    r = client.get("/unsubscribe?token=nope")
    assert r.status_code == 400
    assert client.get("/users/me/settings", headers=alice).json()["notify_deadline_reminders"] is True


def test_unsubscribe_is_rate_limited(client, monkeypatch):
    from app import ratelimit
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    codes = [client.get("/unsubscribe?token=nope").status_code for _ in range(31)]
    assert codes[:30] == [400] * 30 and codes[30] == 429
    ratelimit.reset()

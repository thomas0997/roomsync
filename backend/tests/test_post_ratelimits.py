import pytest

from app import ratelimit

from .conftest import join_room, make_room, signup

DUE = "2026-08-13T15:59:00Z"


@pytest.fixture(autouse=True)
def limiter_on(monkeypatch):
    # conftest.py turns the limiter off for all tests; this file turns it on and clears the counts
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    yield
    ratelimit.reset()


def _setup(client):
    alice = signup(client)  # room creator
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _task(client, rid, headers, title="Quiz"):
    return client.post(f"/rooms/{rid}/tasks", json={"title": title, "type": "quiz", "due_at": DUE}, headers=headers)


def _message(client, rid, headers, body="hi"):
    return client.post(f"/rooms/{rid}/messages", json={"body": body}, headers=headers)


def test_create_task_is_limited_to_20_per_hour_per_user(client):
    alice, bob, rid = _setup(client)
    for i in range(20):
        assert _task(client, rid, alice, f"T{i}").status_code == 201
    r = _task(client, rid, alice, "T20")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    assert _task(client, rid, bob, "Bob's task").status_code == 201  # Bob has his own count


def test_post_message_is_limited_to_30_per_minute_per_user(client):
    alice, bob, rid = _setup(client)
    for i in range(30):
        assert _message(client, rid, alice, f"m{i}").status_code == 201
    r = _message(client, rid, alice, "m30")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    assert _message(client, rid, bob, "from Bob").status_code == 201  # Bob has his own count


def test_a_blocked_message_is_not_saved(client):
    alice, bob, rid = _setup(client)
    for i in range(30):
        assert _message(client, rid, alice, f"m{i}").status_code == 201
    assert _message(client, rid, alice, "blocked").status_code == 429
    bodies = [m["body"] for m in client.get(f"/rooms/{rid}/messages", params={"limit": 100}, headers=bob).json()]
    assert len(bodies) == 30
    assert "blocked" not in bodies


def test_task_and_message_limits_count_separately(client):
    alice, bob, rid = _setup(client)
    for i in range(20):
        assert _task(client, rid, alice, f"T{i}").status_code == 201
    assert _task(client, rid, alice, "T20").status_code == 429  # task limit used up
    assert _message(client, rid, alice, "still fine").status_code == 201  # messages are a different count
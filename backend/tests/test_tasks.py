from .conftest import join_room, make_room, signup

DUE = "2026-08-13T15:59:00Z"


def _setup(client):
    alice = signup(client)  # creates the room, so she is the only admin
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def test_sole_admin_task_is_auto_approved(client):
    alice, bob, rid = _setup(client)
    r = client.post(
        f"/rooms/{rid}/tasks",
        json={"title": "Quiz 1", "type": "quiz", "due_at": DUE},
        headers=alice,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["created_by_name"] == "Alice"
    assert body["room_id"] == rid
    assert body["all_day"] is False
    assert body["due_at"] == DUE


def test_member_task_is_pending(client):
    alice, bob, rid = _setup(client)
    r = client.post(f"/rooms/{rid}/tasks", json={"title": "Exam", "type": "exam", "due_at": DUE}, headers=bob)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"
    assert r.json()["created_by_name"] == "Bob"


def test_non_member_gets_403(client):
    alice, bob, rid = _setup(client)
    carol = signup(client, "c@example.com", "Carol")
    r = client.post(f"/rooms/{rid}/tasks", json={"title": "Exam", "type": "exam", "due_at": DUE}, headers=carol)
    assert r.status_code == 403


def test_no_token_gets_401(client):
    alice, bob, rid = _setup(client)
    r = client.post(f"/rooms/{rid}/tasks", json={"title": "Exam", "type": "exam", "due_at": DUE})
    assert r.status_code == 401


def test_missing_due_at_gets_422(client):
    alice, bob, rid = _setup(client)
    url = f"/rooms/{rid}/tasks"
    assert client.post(url, json={"title": "Exam", "type": "exam"}, headers=alice).status_code == 422
    assert client.post(url, json={"title": "Exam", "type": "exam", "due_at": None}, headers=alice).status_code == 422


def test_bad_input_gets_422(client):
    alice, bob, rid = _setup(client)
    url = f"/rooms/{rid}/tasks"
    assert client.post(url, json={"type": "exam", "due_at": DUE}, headers=alice).status_code == 422  # no title
    assert client.post(url, json={"title": "   ", "type": "exam", "due_at": DUE}, headers=alice).status_code == 422
    assert client.post(url, json={"title": "x", "type": "exam", "due_at": "2026-08-13T15:59:00"}, headers=alice).status_code == 422  # no timezone
    # a client must not be able to choose the status
    assert client.post(url, json={"title": "x", "type": "exam", "due_at": DUE, "status": "approved"}, headers=bob).status_code == 422


def test_due_at_with_offset_is_stored_as_utc(client):
    alice, bob, rid = _setup(client)
    r = client.post(
        f"/rooms/{rid}/tasks",
        json={"title": "Case study", "type": "case-study", "due_at": "2026-08-13T23:59:00+08:00", "all_day": True},
        headers=alice,
    )
    assert r.status_code == 201, r.text
    assert r.json()["due_at"] == DUE
    assert r.json()["all_day"] is True
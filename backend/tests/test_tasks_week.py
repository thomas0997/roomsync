from .conftest import join_room, make_room, signup

# 2026-08-09 is a Sunday. The Manila week is Sun 00:00 to Sat 23:59:59 (UTC+8),
# which in UTC is 2026-08-08T16:00:00Z up to (not including) 2026-08-15T16:00:00Z.
WEEK = "2026-08-09"


def _setup(client):
    alice = signup(client)  # sole admin, so her tasks are auto-approved
    bob = signup(client, "b@example.com", "Bob")  # member, so his tasks are pending
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _add(client, rid, headers, title, due_at):
    r = client.post(f"/rooms/{rid}/tasks", json={"title": title, "type": "quiz", "due_at": due_at}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _week(client, rid, headers, week_start=WEEK):
    return client.get(f"/rooms/{rid}/tasks", params={"week_start": week_start}, headers=headers)


def test_week_boundaries_use_manila_time(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "start of week", "2026-08-08T16:00:00Z")   # Sun 00:00:00 Manila: IN
    _add(client, rid, alice, "end of week", "2026-08-15T15:59:59Z")     # Sat 23:59:59 Manila: IN
    _add(client, rid, alice, "next week", "2026-08-15T16:00:00Z")       # Sun 00:00:00 Manila next week: OUT
    _add(client, rid, alice, "last week", "2026-08-08T15:59:59Z")       # Sat 23:59:59 Manila last week: OUT
    r = _week(client, rid, bob)
    assert r.status_code == 200, r.text
    assert [t["title"] for t in r.json()] == ["start of week", "end of week"]


def test_week_is_sorted_by_due_at(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "third", "2026-08-14T10:00:00Z")
    _add(client, rid, alice, "first", "2026-08-10T10:00:00Z")
    _add(client, rid, alice, "second", "2026-08-12T10:00:00Z")
    r = _week(client, rid, alice)
    assert [t["title"] for t in r.json()] == ["first", "second", "third"]
    assert r.json()[0]["status"] == "approved"
    assert r.json()[0]["due_at"] == "2026-08-10T10:00:00Z"


def test_pending_tasks_are_hidden(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "approved one", "2026-08-12T10:00:00Z")
    pending = _add(client, rid, bob, "pending one", "2026-08-12T11:00:00Z")
    assert pending["status"] == "pending"
    r = _week(client, rid, alice)
    assert [t["title"] for t in r.json()] == ["approved one"]


def test_other_rooms_tasks_are_hidden(client):
    alice, bob, rid = _setup(client)
    other = make_room(client, alice, name="OTHER")
    _add(client, other["id"], alice, "other room task", "2026-08-12T10:00:00Z")
    assert _week(client, rid, alice).json() == []


def test_empty_week_returns_empty_list(client):
    alice, bob, rid = _setup(client)
    r = _week(client, rid, bob)
    assert r.status_code == 200
    assert r.json() == []


def test_no_token_gets_401(client):
    alice, bob, rid = _setup(client)
    r = client.get(f"/rooms/{rid}/tasks", params={"week_start": WEEK})
    assert r.status_code == 401


def test_non_member_gets_403(client):
    alice, bob, rid = _setup(client)
    carol = signup(client, "c@example.com", "Carol")
    assert _week(client, rid, carol).status_code == 403


def test_bad_week_start_gets_422(client):
    alice, bob, rid = _setup(client)
    url = f"/rooms/{rid}/tasks"
    assert client.get(url, headers=alice).status_code == 422                                       # missing
    assert _week(client, rid, alice, "not-a-date").status_code == 422                              # malformed
    assert _week(client, rid, alice, "2026-08-10").status_code == 422                              # a Monday, not a Sunday
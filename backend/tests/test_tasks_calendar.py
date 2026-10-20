from .conftest import join_room, make_room, signup

# August 2026 in Manila (UTC+8) is 2026-07-31T16:00:00Z up to (not including) 2026-08-31T16:00:00Z.
MONTH = "2026-08"


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


def _month(client, rid, headers, month=MONTH):
    return client.get(f"/rooms/{rid}/calendar", params={"month": month}, headers=headers)


def test_month_boundaries_use_manila_time(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "start of month", "2026-07-31T16:00:00Z")  # Aug 1 00:00:00 Manila: IN
    _add(client, rid, alice, "end of month", "2026-08-31T15:59:59Z")    # Aug 31 23:59:59 Manila: IN
    _add(client, rid, alice, "next month", "2026-08-31T16:00:00Z")      # Sep 1 00:00:00 Manila: OUT
    _add(client, rid, alice, "last month", "2026-07-31T15:59:59Z")      # Jul 31 23:59:59 Manila: OUT
    r = _month(client, rid, bob)
    assert r.status_code == 200, r.text
    assert [t["title"] for t in r.json()] == ["start of month", "end of month"]


def test_december_rolls_over_to_next_year(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "dec start", "2026-11-30T16:00:00Z")  # Dec 1 00:00:00 Manila: IN
    _add(client, rid, alice, "dec end", "2026-12-31T15:59:59Z")    # Dec 31 23:59:59 Manila: IN
    _add(client, rid, alice, "january", "2026-12-31T16:00:00Z")    # Jan 1 2027 00:00:00 Manila: OUT
    r = _month(client, rid, alice, "2026-12")
    assert [t["title"] for t in r.json()] == ["dec start", "dec end"]


def test_month_is_sorted_by_due_at(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "third", "2026-08-25T10:00:00Z")
    _add(client, rid, alice, "first", "2026-08-03T10:00:00Z")
    _add(client, rid, alice, "second", "2026-08-14T10:00:00Z")
    r = _month(client, rid, alice)
    assert [t["title"] for t in r.json()] == ["first", "second", "third"]
    assert r.json()[0]["status"] == "approved"
    assert r.json()[0]["due_at"] == "2026-08-03T10:00:00Z"


def test_pending_tasks_are_hidden(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "approved one", "2026-08-12T10:00:00Z")
    pending = _add(client, rid, bob, "pending one", "2026-08-12T11:00:00Z")
    assert pending["status"] == "pending"
    r = _month(client, rid, alice)
    assert [t["title"] for t in r.json()] == ["approved one"]


def test_other_rooms_tasks_are_hidden(client):
    alice, bob, rid = _setup(client)
    other = make_room(client, alice, name="OTHER")
    _add(client, other["id"], alice, "other room task", "2026-08-12T10:00:00Z")
    assert _month(client, rid, alice).json() == []


def test_empty_month_returns_empty_list(client):
    alice, bob, rid = _setup(client)
    r = _month(client, rid, bob)
    assert r.status_code == 200
    assert r.json() == []


def test_no_token_gets_401(client):
    alice, bob, rid = _setup(client)
    r = client.get(f"/rooms/{rid}/calendar", params={"month": MONTH})
    assert r.status_code == 401


def test_non_member_gets_403(client):
    alice, bob, rid = _setup(client)
    carol = signup(client, "c@example.com", "Carol")
    assert _month(client, rid, carol).status_code == 403


def test_bad_month_gets_422(client):
    alice, bob, rid = _setup(client)
    assert client.get(f"/rooms/{rid}/calendar", headers=alice).status_code == 422  # missing
    for bad in ("abc", "2026-13", "2026-00", "2026-8", "2026-08-01", "1999-12"):
        assert _month(client, rid, alice, bad).status_code == 422, bad
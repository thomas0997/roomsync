from .conftest import join_room, make_room, signup

DUE = "2026-08-13T15:59:00Z"


def _setup(client):
    alice = signup(client)  # sole admin, so her tasks are auto-approved
    bob = signup(client, "b@example.com", "Bob")  # member: his tasks are pending
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _add(client, rid, headers, title):
    r = client.post(f"/rooms/{rid}/tasks", json={"title": title, "type": "quiz", "due_at": DUE}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _mine(client, rid, headers, **params):
    return client.get(f"/rooms/{rid}/tasks/mine", params=params, headers=headers)


def test_mine_lists_only_my_tasks_of_every_status_newest_first(client):
    alice, bob, rid = _setup(client)
    t1 = _add(client, rid, bob, "first")
    _add(client, rid, alice, "alice's own")
    t3 = _add(client, rid, bob, "second")
    client.post(f"/tasks/{t1['id']}/approve", headers=alice)
    client.post(f"/tasks/{t3['id']}/reject", headers=alice)
    r = _mine(client, rid, bob)
    assert r.status_code == 200, r.text
    assert [(t["title"], t["status"]) for t in r.json()] == [("second", "rejected"), ("first", "approved")]
    assert [t["title"] for t in _mine(client, rid, alice).json()] == ["alice's own"]


def test_mine_is_empty_when_nothing_submitted(client):
    alice, bob, rid = _setup(client)
    assert _mine(client, rid, bob).json() == []


def test_mine_limit(client):
    alice, bob, rid = _setup(client)
    for i in range(3):
        _add(client, rid, bob, f"t{i}")
    assert [t["title"] for t in _mine(client, rid, bob, limit=2).json()] == ["t2", "t1"]
    assert _mine(client, rid, bob, limit=0).status_code == 422
    assert _mine(client, rid, bob, limit=101).status_code == 422


def test_mine_is_per_room(client):
    alice, bob, rid = _setup(client)
    other = make_room(client, alice, "Other")
    join_room(client, bob, other["invite_code"])
    _add(client, rid, bob, "in first room")
    assert _mine(client, other["id"], bob).json() == []


def test_mine_non_member_gets_403_and_no_token_401(client):
    alice, bob, rid = _setup(client)
    carol = signup(client, "c@example.com", "Carol")
    assert _mine(client, rid, carol).status_code == 403
    assert client.get(f"/rooms/{rid}/tasks/mine").status_code == 401
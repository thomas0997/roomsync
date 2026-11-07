from .conftest import join_room, make_room, signup


def _task(client, h, room_id, title="T"):
    r = client.post(
        f"/rooms/{room_id}/tasks",
        json={"title": title, "type": "quiz", "due_at": "2030-01-01T10:00:00+08:00"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_requires_login(client):
    assert client.get("/users/me/history").status_code == 401


def test_empty_when_nothing_submitted(client):
    h = signup(client)
    assert client.get("/users/me/history", headers=h).json() == []


def test_lists_own_tasks_only_newest_first(client):
    a = signup(client, "a@example.com", "Alice")
    b = signup(client, "b@example.com", "Bob")
    room = make_room(client, a)
    join_room(client, b, room["invite_code"])

    t1 = _task(client, b, room["id"], "First")
    t2 = _task(client, b, room["id"], "Second")
    _task(client, a, room["id"], "Alice's own")  # not Bob's: must not show for Bob
    client.post(f"/tasks/{t1['id']}/approve", headers=a)
    client.post(f"/tasks/{t2['id']}/reject", headers=a)

    r = client.get("/users/me/history", headers=b)
    assert r.status_code == 200
    items = r.json()
    assert [i["title"] for i in items] == ["Second", "First"]  # newest first
    assert items[0]["status"] == "rejected" and items[0]["decided_at"] is not None
    assert items[1]["status"] == "approved"
    assert all(i["room_name"] == room["name"] for i in items)

    assert client.get("/users/me/history", headers=a).json()[0]["title"] == "Alice's own"


def test_includes_pending_tasks(client):
    # A sole admin's own task auto-approves (see routers/tasks.py), so a second member
    # is needed here to get a real pending task.
    a = signup(client, "a@example.com", "Alice")
    b = signup(client, "b@example.com", "Bob")
    room = make_room(client, a)
    join_room(client, b, room["invite_code"])
    _task(client, b, room["id"], "Still waiting")
    items = client.get("/users/me/history", headers=b).json()
    assert items[0]["status"] == "pending" and items[0]["decided_at"] is None


def test_limit_param(client):
    h = signup(client)
    room = make_room(client, h)
    for i in range(3):
        _task(client, h, room["id"], f"T{i}")
    assert len(client.get("/users/me/history?limit=2", headers=h).json()) == 2
    assert client.get("/users/me/history?limit=0", headers=h).status_code == 422

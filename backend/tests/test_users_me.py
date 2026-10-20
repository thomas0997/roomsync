from .conftest import join_room, make_room, signup


def test_get_me_shape(client):
    h = signup(client, "a@example.com", "Alice")
    r = client.get("/users/me", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["email"] == "a@example.com" and d["name"] == "Alice"
    assert d["status"] == {"kind": "working", "text": None}
    assert d["avatar_url"] is None and d["joined_at"]


def test_requires_login(client):
    assert client.get("/users/me").status_code == 401
    assert client.patch("/users/me", json={"name": "x"}).status_code == 401
    assert client.get("/users/me/stats").status_code == 401
    assert client.delete("/users/me").status_code == 401


def test_patch_name_and_status(client):
    h = signup(client)
    r = client.patch("/users/me", json={"name": "  Alicia  ", "status_kind": "brb"}, headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "Alicia" and r.json()["status"] == {"kind": "brb", "text": None}
    assert client.get("/users/me", headers=h).json()["status"]["kind"] == "brb"


def test_custom_status_needs_text(client):
    h = signup(client)
    assert client.patch("/users/me", json={"status_kind": "custom"}, headers=h).status_code == 422
    assert client.patch("/users/me", json={"status_kind": "custom", "status_text": "   "}, headers=h).status_code == 422
    r = client.patch("/users/me", json={"status_kind": "custom", "status_text": "Studying"}, headers=h)
    assert r.json()["status"] == {"kind": "custom", "text": "Studying"}
    # text alone edits the custom status
    r = client.patch("/users/me", json={"status_text": "Napping"}, headers=h)
    assert r.json()["status"]["text"] == "Napping"
    # switching to a preset clears the text
    r = client.patch("/users/me", json={"status_kind": "away", "status_text": "ignored"}, headers=h)
    assert r.json()["status"] == {"kind": "away", "text": None}


def test_patch_validation(client):
    h = signup(client)
    assert client.patch("/users/me", json={}, headers=h).status_code == 422
    assert client.patch("/users/me", json={"name": None}, headers=h).status_code == 422
    assert client.patch("/users/me", json={"name": "   "}, headers=h).status_code == 422
    assert client.patch("/users/me", json={"status_kind": "sleeping"}, headers=h).status_code == 422
    assert client.patch("/users/me", json={"email": "x@y.com"}, headers=h).status_code == 422
    long = "x" * 41
    assert client.patch("/users/me", json={"status_kind": "custom", "status_text": long}, headers=h).status_code == 422


def test_members_list_shows_status(client):
    a = signup(client, "a@example.com", "Alice")
    b = signup(client, "b@example.com", "Bob")
    room = make_room(client, a)
    join_room(client, b, room["invite_code"])
    client.patch("/users/me", json={"status_kind": "custom", "status_text": "Exam week"}, headers=b)
    members = client.get(f"/rooms/{room['id']}/members", headers=a).json()
    bob = next(m for m in members if m["name"] == "Bob")
    assert bob["status"] == {"kind": "custom", "text": "Exam week"}


def _task(client, h, room_id, title="T"):
    r = client.post(
        f"/rooms/{room_id}/tasks",
        json={"title": title, "type": "quiz", "due_at": "2030-01-01T10:00:00+08:00"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_stats(client):
    a = signup(client, "a@example.com", "Alice")
    b = signup(client, "b@example.com", "Bob")
    room = make_room(client, a)
    join_room(client, b, room["invite_code"])
    t1, t2, _ = (_task(client, b, room["id"], f"T{i}") for i in range(3))
    client.post(f"/tasks/{t1['id']}/approve", headers=a)
    client.post(f"/tasks/{t2['id']}/reject", headers=a)
    assert client.get("/users/me/stats", headers=b).json() == {"submitted": 3, "approved": 1, "rejected": 1}
    assert client.get("/users/me/stats", headers=a).json() == {"submitted": 0, "approved": 0, "rejected": 0}


def test_delete_blocked_for_only_admin(client):
    a = signup(client, "a@example.com", "Alice")
    b = signup(client, "b@example.com", "Bob")
    room = make_room(client, a)
    join_room(client, b, room["invite_code"])
    assert client.delete("/users/me", headers=a).status_code == 400
    assert client.get("/users/me", headers=a).status_code == 200  # still there


def test_delete_after_promoting(client):
    a = signup(client, "a@example.com", "Alice")
    b = signup(client, "b@example.com", "Bob")
    room = make_room(client, a)
    join_room(client, b, room["invite_code"])
    bob_id = client.get("/users/me", headers=b).json()["id"]
    assert client.post(f"/rooms/{room['id']}/members/{bob_id}/role", json={"role": "admin"}, headers=a).status_code == 200
    task = _task(client, a, room["id"], "Keep me")
    assert client.delete("/users/me", headers=a).status_code == 204
    # old token and old password no longer work
    assert client.get("/users/me", headers=a).status_code == 401
    r = client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert r.status_code == 401
    # room still exists for Bob, Alice gone from members, her task stays as "Deleted user"
    members = client.get(f"/rooms/{room['id']}/members", headers=b).json()
    assert [m["name"] for m in members] == ["Bob"]
    client.post(f"/tasks/{task['id']}/approve", headers=b)
    week = client.get(f"/rooms/{room['id']}/tasks?week_start=2029-12-30", headers=b).json()
    assert week[0]["created_by_name"] == "Deleted user"


def test_delete_sole_member_removes_room_and_frees_email(client):
    a = signup(client, "a@example.com", "Alice")
    room = make_room(client, a)
    assert client.delete("/users/me", headers=a).status_code == 204
    again = signup(client, "a@example.com", "Alice Again")  # same email can sign up again
    assert client.get("/rooms", headers=again).json() == []
    assert client.get("/users/me", headers=again).json()["name"] == "Alice Again"
    assert room["id"] is not None
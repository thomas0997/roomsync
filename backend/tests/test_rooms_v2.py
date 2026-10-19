from datetime import datetime, timedelta, timezone

from .conftest import join_room, make_room, signup


def _setup(client):
    """Alice creates the room (creator + admin). Bob and Carol join as members."""
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    carol = signup(client, "c@example.com", "Carol")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    join_room(client, carol, room["invite_code"])
    ids = {m["name"]: m["user_id"] for m in client.get(f"/rooms/{room['id']}/members", headers=alice).json()}
    return alice, bob, carol, room, ids


def _promote(client, headers, rid, uid):
    r = client.post(f"/rooms/{rid}/members/{uid}/role", json={"role": "admin"}, headers=headers)
    assert r.status_code == 200, r.text


# ---- PATCH /rooms/{id} ----
def test_admin_can_rename_and_retype(client):
    alice, bob, carol, room, ids = _setup(client)
    r = client.patch(f"/rooms/{room['id']}", json={"name": "  CYB202  ", "type": "team"}, headers=alice)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "CYB202" and r.json()["type"] == "team"
    r = client.patch(f"/rooms/{room['id']}", json={"type": "other"}, headers=alice)  # partial update
    assert r.json()["name"] == "CYB202" and r.json()["type"] == "other"


def test_member_cannot_update_room(client):
    alice, bob, carol, room, ids = _setup(client)
    assert client.patch(f"/rooms/{room['id']}", json={"name": "Hax"}, headers=bob).status_code == 403
    assert client.patch(f"/rooms/{room['id']}", json={"name": "Hax"}).status_code == 401


def test_update_room_bad_input_gets_422(client):
    alice, bob, carol, room, ids = _setup(client)
    url = f"/rooms/{room['id']}"
    assert client.patch(url, json={}, headers=alice).status_code == 422
    assert client.patch(url, json={"type": "palace"}, headers=alice).status_code == 422
    assert client.patch(url, json={"name": ""}, headers=alice).status_code == 422
    assert client.patch(url, json={"name": "x", "created_by": 99}, headers=alice).status_code == 422


# ---- remove member ----
def test_admin_removes_member_and_they_lose_access(client):
    alice, bob, carol, room, ids = _setup(client)
    rid = room["id"]
    assert client.delete(f"/rooms/{rid}/members/{ids['Bob']}", headers=alice).status_code == 204
    assert client.get(f"/rooms/{rid}/members", headers=bob).status_code == 403
    names = [m["name"] for m in client.get(f"/rooms/{rid}/members", headers=alice).json()]
    assert names == ["Alice", "Carol"]


def test_member_cannot_remove_anyone(client):
    alice, bob, carol, room, ids = _setup(client)
    rid = room["id"]
    assert client.delete(f"/rooms/{rid}/members/{ids['Carol']}", headers=bob).status_code == 403
    assert client.delete(f"/rooms/{rid}/members/{ids['Carol']}").status_code == 401


def test_remove_unknown_member_gets_404(client):
    alice, bob, carol, room, ids = _setup(client)
    dave = signup(client, "d@example.com", "Dave")
    dave_id = client.get("/auth/me", headers=dave).json()["id"]
    assert client.delete(f"/rooms/{room['id']}/members/{dave_id}", headers=alice).status_code == 404


def test_only_creator_removes_admins_and_creator_is_safe(client):
    alice, bob, carol, room, ids = _setup(client)
    rid = room["id"]
    _promote(client, alice, rid, ids["Bob"])
    _promote(client, alice, rid, ids["Carol"])
    # Bob is an admin but not the creator
    assert client.delete(f"/rooms/{rid}/members/{ids['Carol']}", headers=bob).status_code == 403
    assert client.delete(f"/rooms/{rid}/members/{ids['Alice']}", headers=bob).status_code == 400
    # The creator can remove an admin, but not herself
    assert client.delete(f"/rooms/{rid}/members/{ids['Alice']}", headers=alice).status_code == 400
    assert client.delete(f"/rooms/{rid}/members/{ids['Carol']}", headers=alice).status_code == 204


# ---- invite code reset ----
def test_reset_invite_code_kills_the_old_one(client):
    alice, bob, carol, room, ids = _setup(client)
    old = room["invite_code"]
    r = client.post(f"/rooms/{room['id']}/invite-code/reset", headers=alice)
    assert r.status_code == 200, r.text
    new = r.json()["invite_code"]
    assert new != old and len(new) == 8
    dave = signup(client, "d@example.com", "Dave")
    assert client.post("/rooms/join", json={"invite_code": old}, headers=dave).status_code == 404
    assert client.post("/rooms/join", json={"invite_code": new}, headers=dave).status_code == 200


def test_member_cannot_reset_invite_code(client):
    alice, bob, carol, room, ids = _setup(client)
    url = f"/rooms/{room['id']}/invite-code/reset"
    assert client.post(url, headers=bob).status_code == 403
    assert client.post(url).status_code == 401


# ---- type + pending_count in room info ----
def test_room_has_type_and_pending_count(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    r = client.post("/rooms", json={"name": "Study", "type": "study_group"}, headers=alice)
    assert r.status_code == 201 and r.json()["type"] == "study_group" and r.json()["pending_count"] == 0
    room = r.json()
    join_room(client, bob, room["invite_code"])
    due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    t = client.post(f"/rooms/{room['id']}/tasks", json={"title": "Quiz", "type": "quiz", "due_at": due}, headers=bob)
    assert t.status_code == 201 and t.json()["status"] == "pending"
    for h in (alice, bob):  # same number for admins and members
        rooms = client.get("/rooms", headers=h).json()
        assert rooms[0]["pending_count"] == 1
    assert client.post("/rooms", json={"name": "Default"}, headers=alice).json()["type"] == "classroom"
    assert client.post("/rooms", json={"name": "Bad", "type": "palace"}, headers=alice).status_code == 422
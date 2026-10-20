from .conftest import join_room, make_room, signup

DUE = "2026-08-13T15:59:00Z"


def _setup(client):
    alice = signup(client)  # room creator, so the first admin
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    bob_id = client.get("/auth/me", headers=bob).json()["id"]
    return alice, bob, room["id"], bob_id


def _set_role(client, rid, user_id, headers, role):
    return client.post(f"/rooms/{rid}/members/{user_id}/role", json={"role": role}, headers=headers)


def _add(client, rid, headers, title):
    r = client.post(f"/rooms/{rid}/tasks", json={"title": title, "type": "quiz", "due_at": DUE}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_admin_task_stays_pending_when_another_admin_exists(client):
    alice, bob, rid, bob_id = _setup(client)
    r = _set_role(client, rid, bob_id, alice, "admin")  # Alice promotes Bob: two admins now
    assert r.status_code == 200, r.text
    assert _add(client, rid, alice, "Alice quiz")["status"] == "pending"
    assert _add(client, rid, bob, "Bob quiz")["status"] == "pending"


def test_sole_admin_task_is_auto_approved_again_after_demotion(client):
    alice, bob, rid, bob_id = _setup(client)
    assert _set_role(client, rid, bob_id, alice, "admin").status_code == 200
    assert _set_role(client, rid, bob_id, alice, "member").status_code == 200  # only the creator can demote
    assert _add(client, rid, alice, "Alice quiz")["status"] == "approved"
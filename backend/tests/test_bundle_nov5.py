"""Nov 5 bundle: 15-char custom tag, task notes, admin edit of approved tasks, Approve all, room icon."""
import io

from PIL import Image

from .conftest import join_room, make_room, signup

DUE = "2026-08-13T15:59:00Z"


def _setup(client):
    alice = signup(client)  # sole admin: her tasks are auto-approved
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _add(client, rid, headers, title="Quiz", **extra):
    body = {"title": title, "type": "quiz", "due_at": DUE, **extra}
    r = client.post(f"/rooms/{rid}/tasks", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _png():
    out = io.BytesIO()
    Image.new("RGB", (60, 40), (10, 120, 200)).save(out, "PNG")
    return out.getvalue()


# ---------- custom tag: 1 to 15 characters ----------

def test_type_of_15_characters_is_ok_and_16_is_not(client):
    alice, bob, rid = _setup(client)
    ok = client.post(f"/rooms/{rid}/tasks", json={"title": "x", "type": "a" * 15, "due_at": DUE}, headers=alice)
    assert ok.status_code == 201 and ok.json()["type"] == "a" * 15
    bad = client.post(f"/rooms/{rid}/tasks", json={"title": "x", "type": "a" * 16, "due_at": DUE}, headers=alice)
    assert bad.status_code == 422
    t = _add(client, rid, alice)
    assert client.patch(f"/tasks/{t['id']}", json={"type": "b" * 16}, headers=alice).status_code == 422


# ---------- notes ----------

def test_note_on_create_edit_and_clear(client):
    alice, bob, rid = _setup(client)
    t = _add(client, rid, bob, note="Bring a calculator")
    assert t["note"] == "Bring a calculator"
    r = client.patch(f"/tasks/{t['id']}", json={"note": "Room 204"}, headers=bob)
    assert r.status_code == 200 and r.json()["note"] == "Room 204"
    r = client.patch(f"/tasks/{t['id']}", json={"note": None}, headers=bob)
    assert r.json()["note"] is None
    assert _add(client, rid, bob, note="   ")["note"] is None  # blank note is no note


def test_note_longer_than_300_is_422(client):
    alice, bob, rid = _setup(client)
    body = {"title": "x", "type": "quiz", "due_at": DUE, "note": "n" * 301}
    assert client.post(f"/rooms/{rid}/tasks", json=body, headers=alice).status_code == 422
    t = _add(client, rid, alice)
    assert client.patch(f"/tasks/{t['id']}", json={"note": "n" * 301}, headers=alice).status_code == 422


# ---------- admin edit of approved tasks ----------

def test_admin_can_edit_approved_task_and_it_is_marked_edited(client):
    alice, bob, rid = _setup(client)
    t = _add(client, rid, alice)  # auto-approved
    assert t["status"] == "approved" and t["edited_by_name"] is None
    r = client.patch(f"/tasks/{t['id']}", json={"title": "Quiz (new title)", "note": "Moved"}, headers=alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Quiz (new title)" and body["status"] == "approved"
    assert body["edited_by_name"] == "Alice" and body["edited_at"].endswith("Z")


def test_member_cannot_edit_approved_task_even_their_own(client):
    alice, bob, rid = _setup(client)
    t = _add(client, rid, bob)
    client.post(f"/tasks/{t['id']}/approve", headers=alice)
    r = client.patch(f"/tasks/{t['id']}", json={"title": "Sneaky"}, headers=bob)
    assert r.status_code == 403
    assert client.patch(f"/tasks/{t['id']}", json={"title": "Sneaky"}).status_code == 401


def test_pending_edit_is_not_marked_edited_and_rejected_is_locked(client):
    alice, bob, rid = _setup(client)
    t = _add(client, rid, bob)
    r = client.patch(f"/tasks/{t['id']}", json={"title": "Fixed"}, headers=bob)
    assert r.json()["edited_by_name"] is None and r.json()["status"] == "pending"
    client.post(f"/tasks/{t['id']}/reject", headers=alice)
    assert client.patch(f"/tasks/{t['id']}", json={"title": "Again"}, headers=alice).status_code == 403


def test_outsider_gets_404_on_edit(client):
    alice, bob, rid = _setup(client)
    t = _add(client, rid, alice)
    eve = signup(client, "e@example.com", "Eve")
    assert client.patch(f"/tasks/{t['id']}", json={"title": "x"}, headers=eve).status_code == 404


# ---------- Approve all ----------

def test_approve_all_approves_every_pending_task(client):
    alice, bob, rid = _setup(client)
    for n in range(3):
        _add(client, rid, bob, f"Task {n}")
    r = client.post(f"/rooms/{rid}/approvals/approve-all", headers=alice)
    assert r.status_code == 200 and r.json() == {"approved": 3, "skipped": 0}
    assert client.get(f"/rooms/{rid}/approvals", headers=alice).json() == []
    assert client.post(f"/rooms/{rid}/approvals/approve-all", headers=alice).json() == {"approved": 0, "skipped": 0}


def test_approve_all_skips_my_own_when_there_is_another_admin(client):
    alice, bob, rid = _setup(client)
    members = client.get(f"/rooms/{rid}/members", headers=alice).json()
    bob_id = next(m["user_id"] for m in members if m["name"] == "Bob")
    assert client.post(f"/rooms/{rid}/members/{bob_id}/role", json={"role": "admin"}, headers=alice).status_code == 200
    _add(client, rid, alice, "Alice's own")  # pending now: two admins
    _add(client, rid, bob, "Bob's own")
    r = client.post(f"/rooms/{rid}/approvals/approve-all", headers=alice)
    assert r.json() == {"approved": 1, "skipped": 1}


def test_approve_all_is_admin_only(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, bob)
    assert client.post(f"/rooms/{rid}/approvals/approve-all", headers=bob).status_code == 403
    assert client.post(f"/rooms/{rid}/approvals/approve-all").status_code == 401
    eve = signup(client, "e@example.com", "Eve")
    assert client.post(f"/rooms/{rid}/approvals/approve-all", headers=eve).status_code == 403


# ---------- room icon ----------

def _put(client, rid, headers, data):
    return client.put(f"/rooms/{rid}/avatar", content=data, headers={**headers, "Content-Type": "image/png"})


def test_admin_sets_room_icon_members_can_see_it(client):
    alice, bob, rid = _setup(client)
    assert client.get(f"/rooms/{rid}/avatar", headers=bob).status_code == 404  # no icon yet
    r = _put(client, rid, alice, _png())
    assert r.status_code == 200 and r.json()["avatar_url"].startswith(f"/rooms/{rid}/avatar?v=")
    got = client.get(f"/rooms/{rid}/avatar", headers=bob)
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(got.content)).size == (256, 256)
    rooms = client.get("/rooms", headers=bob).json()
    assert rooms[0]["avatar_url"].startswith(f"/rooms/{rid}/avatar")


def test_room_icon_rules(client):
    alice, bob, rid = _setup(client)
    assert _put(client, rid, bob, _png()).status_code == 403          # members cannot change it
    assert client.put(f"/rooms/{rid}/avatar", content=_png()).status_code == 401
    assert _put(client, rid, alice, b"not an image").status_code == 422
    assert _put(client, rid, alice, b"").status_code == 422
    eve = signup(client, "e@example.com", "Eve")
    assert client.get(f"/rooms/{rid}/avatar", headers=eve).status_code == 403  # outsiders cannot see it


def test_admin_can_remove_room_icon(client):
    alice, bob, rid = _setup(client)
    _put(client, rid, alice, _png())
    assert client.delete(f"/rooms/{rid}/avatar", headers=bob).status_code == 403
    assert client.delete(f"/rooms/{rid}/avatar", headers=alice).status_code == 204
    assert client.get(f"/rooms/{rid}/avatar", headers=bob).status_code == 404
    assert client.get("/rooms", headers=bob).json()[0]["avatar_url"] is None

import time

from .conftest import join_room, make_room, signup

DUE = "2026-08-13T15:59:00Z"
WEEK = "2026-08-09"  # a Sunday; DUE falls inside this Manila week


def _setup(client):
    alice = signup(client)  # room creator and first admin
    bob = signup(client, "b@example.com", "Bob")  # member
    carol = signup(client, "c@example.com", "Carol")  # member
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    join_room(client, carol, room["invite_code"])
    return alice, bob, carol, room["id"]


def _add(client, rid, headers, title, due_at=DUE):
    r = client.post(f"/rooms/{rid}/tasks", json={"title": title, "type": "quiz", "due_at": due_at}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _approve(client, task_id, headers):
    return client.post(f"/tasks/{task_id}/approve", headers=headers)


def _reject(client, task_id, headers):
    return client.post(f"/tasks/{task_id}/reject", headers=headers)


def _pending(client, rid, headers):
    return client.get(f"/rooms/{rid}/approvals", headers=headers)


def _history(client, rid, headers, **params):
    return client.get(f"/rooms/{rid}/approvals/history", params=params, headers=headers)


def _board(client, rid, headers):
    return client.get(f"/rooms/{rid}/tasks", params={"week_start": WEEK}, headers=headers)


def _user_id(client, headers):
    return client.get("/auth/me", headers=headers).json()["id"]


def _set_role(client, rid, user_id, headers, role):
    r = client.post(f"/rooms/{rid}/members/{user_id}/role", json={"role": role}, headers=headers)
    assert r.status_code == 200, r.text


def _pending_count(client, rid, headers):
    rooms = client.get("/rooms", headers=headers).json()
    return next(r["pending_count"] for r in rooms if r["id"] == rid)


# ---------- approve and reject ----------

def test_admin_approves_member_task_and_it_reaches_the_board(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    assert t["status"] == "pending"
    assert _board(client, rid, carol).json() == []  # pending tasks stay off the board
    r = _approve(client, t["id"], alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["decided_by_name"] == "Alice"
    assert body["decided_at"] is not None
    assert body["created_by_name"] == "Bob"
    assert [x["title"] for x in _board(client, rid, carol).json()] == ["Quiz 1"]


def test_admin_rejects_member_task_and_it_stays_off_the_board(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    r = _reject(client, t["id"], alice)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
    assert r.json()["decided_by_name"] == "Alice"
    assert _board(client, rid, carol).json() == []


def test_member_cannot_decide(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    assert _approve(client, t["id"], carol).status_code == 403
    assert _reject(client, t["id"], carol).status_code == 403
    assert _approve(client, t["id"], bob).status_code == 403  # even the creator
    assert [x["title"] for x in _pending(client, rid, alice).json()] == ["Quiz 1"]  # still pending


def test_non_member_and_missing_task_get_404(client):
    alice, bob, carol, rid = _setup(client)
    dave = signup(client, "d@example.com", "Dave")  # not in the room
    t = _add(client, rid, bob, "Quiz 1")
    assert _approve(client, t["id"], dave).status_code == 404
    assert _reject(client, t["id"], dave).status_code == 404
    assert _approve(client, 9999, alice).status_code == 404
    assert _reject(client, 9999, alice).status_code == 404


def test_decide_without_token_gets_401(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    assert client.post(f"/tasks/{t['id']}/approve").status_code == 401
    assert client.post(f"/tasks/{t['id']}/reject").status_code == 401


def test_first_decision_is_final(client):
    alice, bob, carol, rid = _setup(client)
    t1 = _add(client, rid, bob, "Quiz 1")
    assert _approve(client, t1["id"], alice).status_code == 200
    r = _approve(client, t1["id"], alice)
    assert r.status_code == 409
    assert r.json()["detail"] == "Task already decided"
    assert _reject(client, t1["id"], alice).status_code == 409
    t2 = _add(client, rid, bob, "Quiz 2")
    assert _reject(client, t2["id"], alice).status_code == 200
    assert _approve(client, t2["id"], alice).status_code == 409
    assert [x["title"] for x in _board(client, rid, carol).json()] == ["Quiz 1"]  # the rejected one never appears


def test_admin_cannot_decide_own_task_when_another_admin_exists(client):
    alice, bob, carol, rid = _setup(client)
    _set_role(client, rid, _user_id(client, bob), alice, "admin")  # two admins now
    t = _add(client, rid, bob, "Bob's quiz")
    assert t["status"] == "pending"
    assert _approve(client, t["id"], bob).status_code == 403
    assert _reject(client, t["id"], bob).status_code == 403
    assert _approve(client, t["id"], alice).status_code == 200  # the other admin can


def test_sole_admin_can_decide_own_older_pending_task(client):
    alice, bob, carol, rid = _setup(client)
    bob_id = _user_id(client, bob)
    _set_role(client, rid, bob_id, alice, "admin")  # two admins, so Alice's task stays pending
    t = _add(client, rid, alice, "Alice's quiz")
    assert t["status"] == "pending"
    _set_role(client, rid, bob_id, alice, "member")  # Alice is the only admin again
    r = _approve(client, t["id"], alice)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


def test_admin_of_another_room_gets_404(client):
    alice, bob, carol, rid = _setup(client)
    erin = signup(client, "e@example.com", "Erin")
    frank = signup(client, "f@example.com", "Frank")
    other = make_room(client, erin, name="OTHER")
    join_room(client, frank, other["invite_code"])
    t = _add(client, other["id"], frank, "Other room quiz")
    assert _approve(client, t["id"], alice).status_code == 404  # Alice is not in that room
    assert _reject(client, t["id"], alice).status_code == 404
    assert _approve(client, t["id"], erin).status_code == 200  # that room's own admin can


# ---------- pending list ----------

def test_pending_list_is_oldest_first_and_pending_only(client):
    alice, bob, carol, rid = _setup(client)
    _add(client, rid, alice, "auto approved")  # sole admin: approved at once, never pending
    _add(client, rid, bob, "first")
    _add(client, rid, carol, "second")
    r = _pending(client, rid, alice)
    assert r.status_code == 200, r.text
    assert [t["title"] for t in r.json()] == ["first", "second"]
    assert all(t["status"] == "pending" for t in r.json())
    assert _approve(client, r.json()[0]["id"], alice).status_code == 200
    assert [t["title"] for t in _pending(client, rid, alice).json()] == ["second"]  # decided tasks leave the list


def test_pending_list_is_admin_only(client):
    alice, bob, carol, rid = _setup(client)
    dave = signup(client, "d@example.com", "Dave")
    _add(client, rid, bob, "Quiz 1")
    assert _pending(client, rid, bob).status_code == 403
    assert _pending(client, rid, dave).status_code == 403
    assert _pending(client, rid, alice).status_code == 200


def test_pending_list_without_token_gets_401(client):
    alice, bob, carol, rid = _setup(client)
    assert client.get(f"/rooms/{rid}/approvals").status_code == 401


def test_other_rooms_tasks_are_not_listed(client):
    alice, bob, carol, rid = _setup(client)
    erin = signup(client, "e@example.com", "Erin")
    frank = signup(client, "f@example.com", "Frank")
    other = make_room(client, erin, name="OTHER")
    join_room(client, frank, other["invite_code"])
    _add(client, other["id"], frank, "other room task")
    _add(client, rid, bob, "mine")
    assert [t["title"] for t in _pending(client, rid, alice).json()] == ["mine"]
    assert _history(client, rid, alice).json() == []


# ---------- history ----------

def test_history_lists_only_explicit_decisions_newest_first(client):
    alice, bob, carol, rid = _setup(client)
    _add(client, rid, alice, "auto approved")  # not an explicit decision: must not appear
    a = _add(client, rid, bob, "A")
    b = _add(client, rid, carol, "B")
    _add(client, rid, bob, "C still pending")  # not decided: must not appear
    assert _reject(client, b["id"], alice).status_code == 200
    time.sleep(0.05)
    assert _approve(client, a["id"], alice).status_code == 200  # decided last, so it comes first
    r = _history(client, rid, alice)
    assert r.status_code == 200, r.text
    assert [t["title"] for t in r.json()] == ["A", "B"]
    assert [t["status"] for t in r.json()] == ["approved", "rejected"]
    assert r.json()[0]["decided_by_name"] == "Alice"
    assert r.json()[0]["decided_at"] is not None


def test_history_limit(client):
    alice, bob, carol, rid = _setup(client)
    for i in range(3):
        t = _add(client, rid, bob, f"T{i}")
        assert _approve(client, t["id"], alice).status_code == 200
        time.sleep(0.05)
    r = _history(client, rid, alice, limit=2)
    assert [t["title"] for t in r.json()] == ["T2", "T1"]
    assert len(_history(client, rid, alice).json()) == 3  # default limit is 50


def test_history_is_admin_only(client):
    alice, bob, carol, rid = _setup(client)
    dave = signup(client, "d@example.com", "Dave")
    assert _history(client, rid, bob).status_code == 403
    assert _history(client, rid, dave).status_code == 403
    assert client.get(f"/rooms/{rid}/approvals/history").status_code == 401
    assert _history(client, rid, alice).status_code == 200


def test_history_bad_limit_gets_422(client):
    alice, bob, carol, rid = _setup(client)
    for bad in (0, 201, -1, "abc"):
        assert _history(client, rid, alice, limit=bad).status_code == 422, bad
    assert _history(client, rid, alice, limit=1).status_code == 200
    assert _history(client, rid, alice, limit=200).status_code == 200


# ---------- pending_count (lives in rooms.py, reads the same tasks) ----------

def test_pending_count_follows_decisions(client):
    alice, bob, carol, rid = _setup(client)
    a = _add(client, rid, bob, "A")
    b = _add(client, rid, carol, "B")
    assert _pending_count(client, rid, alice) == 2
    assert _pending_count(client, rid, bob) == 2  # same number for members
    assert _approve(client, a["id"], alice).status_code == 200
    assert _pending_count(client, rid, alice) == 1
    assert _reject(client, b["id"], alice).status_code == 200
    assert _pending_count(client, rid, alice) == 0
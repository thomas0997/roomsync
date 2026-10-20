from .conftest import join_room, make_room, signup

DUE = "2026-08-13T15:59:00Z"
WEEK = "2026-08-09"  # a Sunday; DUE falls inside this Manila week


def _setup(client):
    alice = signup(client)  # room creator and sole admin, so her tasks are auto-approved
    bob = signup(client, "b@example.com", "Bob")  # member: his tasks are pending
    carol = signup(client, "c@example.com", "Carol")  # another member
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    join_room(client, carol, room["invite_code"])
    return alice, bob, carol, room["id"]


def _add(client, rid, headers, title, due_at=DUE, **extra):
    body = {"title": title, "type": "quiz", "due_at": due_at, **extra}
    r = client.post(f"/rooms/{rid}/tasks", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _patch(client, task_id, headers, body):
    return client.patch(f"/tasks/{task_id}", json=body, headers=headers)


def _week(client, rid, headers):
    return client.get(f"/rooms/{rid}/tasks", params={"week_start": WEEK}, headers=headers)


# ---------- PATCH /tasks/{task_id} ----------

def test_creator_can_edit_pending_task(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1", subject="Math")
    r = _patch(client, t["id"], bob, {"title": "Quiz 1 (moved)", "type": "exam"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Quiz 1 (moved)"
    assert body["type"] == "exam"
    assert body["subject"] == "Math"  # not sent, so unchanged
    assert body["status"] == "pending"  # editing never changes the status
    assert body["created_by_name"] == "Bob"


def test_partial_edit_keeps_other_fields(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    r = _patch(client, t["id"], bob, {"all_day": True})
    assert r.status_code == 200, r.text
    assert r.json()["all_day"] is True
    assert r.json()["title"] == "Quiz 1"
    assert r.json()["due_at"] == DUE


def test_edit_due_at_with_offset_is_stored_as_utc(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    r = _patch(client, t["id"], bob, {"due_at": "2026-08-14T23:59:00+08:00"})
    assert r.status_code == 200, r.text
    assert r.json()["due_at"] == "2026-08-14T15:59:00Z"


def test_subject_can_be_cleared_with_null(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1", subject="Math")
    r = _patch(client, t["id"], bob, {"subject": None})
    assert r.status_code == 200, r.text
    assert r.json()["subject"] is None


def test_only_the_creator_can_edit(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    assert _patch(client, t["id"], carol, {"title": "Hacked"}).status_code == 403  # other member
    assert _patch(client, t["id"], alice, {"title": "Hacked"}).status_code == 403  # even an admin
    assert _patch(client, t["id"], bob, {"title": "Fine"}).status_code == 200      # the creator


def test_approved_task_cannot_be_edited(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, alice, "Approved quiz")  # sole admin, so auto-approved
    assert t["status"] == "approved"
    assert _patch(client, t["id"], alice, {"title": "Changed"}).status_code == 403


def test_edit_by_non_member_gets_404(client):
    alice, bob, carol, rid = _setup(client)
    dave = signup(client, "d@example.com", "Dave")
    t = _add(client, rid, bob, "Quiz 1")
    assert _patch(client, t["id"], dave, {"title": "x"}).status_code == 404


def test_edit_missing_task_gets_404(client):
    alice, bob, carol, rid = _setup(client)
    assert _patch(client, 9999, alice, {"title": "x"}).status_code == 404


def test_edit_without_token_gets_401(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    assert client.patch(f"/tasks/{t['id']}", json={"title": "x"}).status_code == 401


def test_edit_bad_input_gets_422(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    bad_bodies = [
        {},                                    # nothing to change
        {"title": None},                       # null title
        {"type": None},                        # null type
        {"due_at": None},                      # due_at can never be null
        {"all_day": None},                     # null all_day
        {"title": "   "},                      # blank title
        {"type": ""},                          # empty type
        {"due_at": "2026-08-14T10:00:00"},     # no time zone
        {"status": "approved"},                # a client must not choose the status
        {"title": "x" * 201},                  # too long
    ]
    for bad in bad_bodies:
        assert _patch(client, t["id"], bob, bad).status_code == 422, bad


# ---------- DELETE /tasks/{task_id} ----------

def test_creator_can_delete_own_pending_task(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    r = client.delete(f"/tasks/{t['id']}", headers=bob)
    assert r.status_code == 204
    assert client.delete(f"/tasks/{t['id']}", headers=bob).status_code == 404  # it is gone


def test_admin_can_delete_a_members_task(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    assert client.delete(f"/tasks/{t['id']}", headers=alice).status_code == 204


def test_other_member_cannot_delete(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    assert client.delete(f"/tasks/{t['id']}", headers=carol).status_code == 403
    assert client.delete(f"/tasks/{t['id']}", headers=bob).status_code == 204  # still there for its creator


def test_deleted_approved_task_leaves_the_board(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, alice, "Approved quiz")
    assert [x["title"] for x in _week(client, rid, bob).json()] == ["Approved quiz"]
    assert client.delete(f"/tasks/{t['id']}", headers=alice).status_code == 204
    assert _week(client, rid, bob).json() == []


def test_delete_by_non_member_or_missing_task_gets_404(client):
    alice, bob, carol, rid = _setup(client)
    dave = signup(client, "d@example.com", "Dave")
    t = _add(client, rid, bob, "Quiz 1")
    assert client.delete(f"/tasks/{t['id']}", headers=dave).status_code == 404
    assert client.delete("/tasks/9999", headers=alice).status_code == 404


def test_delete_without_token_gets_401(client):
    alice, bob, carol, rid = _setup(client)
    t = _add(client, rid, bob, "Quiz 1")
    assert client.delete(f"/tasks/{t['id']}").status_code == 401
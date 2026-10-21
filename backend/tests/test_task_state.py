from .conftest import join_room, make_room, signup

WEEK = "2026-08-09"
DUE = "2026-08-12T10:00:00Z"


def _setup(client):
    alice = signup(client)  # sole admin, so her tasks are auto-approved
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _add(client, rid, headers, title="Quiz 1", due_at=DUE):
    r = client.post(f"/rooms/{rid}/tasks", json={"title": title, "type": "quiz", "due_at": due_at}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _week(client, rid, headers):
    r = client.get(f"/rooms/{rid}/tasks", params={"week_start": WEEK}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _month(client, rid, headers):
    r = client.get(f"/rooms/{rid}/calendar", params={"month": "2026-08"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _removed(client, rid, headers):
    r = client.get(f"/rooms/{rid}/tasks/removed", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_done_defaults_to_false(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice)
    assert _week(client, rid, alice)[0]["done"] is False
    assert _month(client, rid, bob)[0]["done"] is False


def test_tick_and_untick(client):
    alice, bob, rid = _setup(client)
    tid = _add(client, rid, alice)["id"]
    r = client.put(f"/tasks/{tid}/done", headers=bob)
    assert r.status_code == 200 and r.json()["done"] is True
    assert _week(client, rid, bob)[0]["done"] is True
    assert _month(client, rid, bob)[0]["done"] is True
    r = client.delete(f"/tasks/{tid}/done", headers=bob)
    assert r.status_code == 200 and r.json()["done"] is False
    assert _week(client, rid, bob)[0]["done"] is False


def test_done_is_per_user(client):
    alice, bob, rid = _setup(client)
    tid = _add(client, rid, alice)["id"]
    client.put(f"/tasks/{tid}/done", headers=bob)
    assert _week(client, rid, bob)[0]["done"] is True
    assert _week(client, rid, alice)[0]["done"] is False  # Alice's board is untouched


def test_tick_twice_and_untick_when_never_ticked_are_fine(client):
    alice, bob, rid = _setup(client)
    tid = _add(client, rid, alice)["id"]
    assert client.put(f"/tasks/{tid}/done", headers=bob).status_code == 200
    assert client.put(f"/tasks/{tid}/done", headers=bob).status_code == 200
    assert client.delete(f"/tasks/{tid}/done", headers=bob).status_code == 200
    assert client.delete(f"/tasks/{tid}/done", headers=bob).status_code == 200
    assert _week(client, rid, bob)[0]["done"] is False


def test_remove_hides_from_week_only_for_that_user(client):
    alice, bob, rid = _setup(client)
    tid = _add(client, rid, alice)["id"]
    r = client.put(f"/tasks/{tid}/hidden", headers=bob)
    assert r.status_code == 200
    assert _week(client, rid, bob) == []
    assert len(_week(client, rid, alice)) == 1  # Alice still sees it


def test_calendar_still_shows_removed_task(client):
    alice, bob, rid = _setup(client)
    tid = _add(client, rid, alice)["id"]
    client.put(f"/tasks/{tid}/hidden", headers=bob)
    assert len(_month(client, rid, bob)) == 1


def test_removed_list_and_restore(client):
    alice, bob, rid = _setup(client)
    t1 = _add(client, rid, alice, "later", "2026-08-14T10:00:00Z")["id"]
    t2 = _add(client, rid, alice, "sooner", "2026-08-10T10:00:00Z")["id"]
    assert _removed(client, rid, bob) == []
    client.put(f"/tasks/{t1}/hidden", headers=bob)
    client.put(f"/tasks/{t2}/hidden", headers=bob)
    assert [t["title"] for t in _removed(client, rid, bob)] == ["sooner", "later"]
    assert _removed(client, rid, alice) == []  # per user
    r = client.delete(f"/tasks/{t2}/hidden", headers=bob)
    assert r.status_code == 200
    assert [t["title"] for t in _removed(client, rid, bob)] == ["later"]
    assert [t["title"] for t in _week(client, rid, bob)] == ["sooner"]


def test_done_and_hidden_are_independent(client):
    alice, bob, rid = _setup(client)
    tid = _add(client, rid, alice)["id"]
    client.put(f"/tasks/{tid}/done", headers=bob)
    client.put(f"/tasks/{tid}/hidden", headers=bob)
    client.delete(f"/tasks/{tid}/hidden", headers=bob)  # restore keeps the tick
    assert _week(client, rid, bob)[0]["done"] is True
    client.put(f"/tasks/{tid}/hidden", headers=bob)
    client.delete(f"/tasks/{tid}/done", headers=bob)  # untick keeps it removed
    assert _week(client, rid, bob) == []
    assert _removed(client, rid, bob)[0]["done"] is False


def test_pending_task_cannot_be_ticked_or_removed(client):
    alice, bob, rid = _setup(client)
    tid = _add(client, rid, bob)["id"]  # Bob is a member, so this is pending
    assert client.put(f"/tasks/{tid}/done", headers=bob).status_code == 409
    assert client.put(f"/tasks/{tid}/hidden", headers=bob).status_code == 409


def test_non_member_missing_task_and_no_token(client):
    alice, bob, rid = _setup(client)
    tid = _add(client, rid, alice)["id"]
    carol = signup(client, "c@example.com", "Carol")
    for method in (client.put, client.delete):
        for kind in ("done", "hidden"):
            assert method(f"/tasks/{tid}/{kind}", headers=carol).status_code == 404
            assert method(f"/tasks/99999/{kind}", headers=bob).status_code == 404
            assert method(f"/tasks/{tid}/{kind}").status_code == 401
    assert client.get(f"/rooms/{rid}/tasks/removed", headers=carol).status_code == 403
    assert client.get(f"/rooms/{rid}/tasks/removed").status_code == 401


def test_deleting_a_task_removes_its_state(client):
    alice, bob, rid = _setup(client)
    tid = _add(client, rid, alice)["id"]
    client.put(f"/tasks/{tid}/done", headers=bob)
    client.put(f"/tasks/{tid}/hidden", headers=bob)
    assert client.delete(f"/tasks/{tid}", headers=alice).status_code == 204
    assert _removed(client, rid, bob) == []
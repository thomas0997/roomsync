"""Attach notes (room files) to tasks, and `used_in` on the Notes page."""
import pytest

from app import ratelimit
from app.db import SessionLocal
from app.models import TaskFile

from .conftest import join_room, make_room, signup

DUE = "2030-01-15T15:59:00Z"


def _setup(client):
    alice = signup(client, "a@example.com", "Alice")  # creates the room: admin
    bob = signup(client, "b@example.com", "Bob")  # member
    carol = signup(client, "c@example.com", "Carol")  # member
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    join_room(client, carol, room["invite_code"])
    return alice, bob, carol, room["id"]


def _file(client, headers, rid, name="n.txt"):
    r = client.post(f"/rooms/{rid}/files", params={"name": name}, content=b"hello\n",
                    headers={**headers, "Content-Type": "application/octet-stream"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _task(client, headers, rid, title="T", **extra):
    r = client.post(f"/rooms/{rid}/tasks", json={"title": title, "type": "quiz", "due_at": DUE, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _put(client, headers, task_id, file_id):
    return client.put(f"/tasks/{task_id}/attachments/{file_id}", headers=headers)


def _del(client, headers, task_id, file_id):
    return client.delete(f"/tasks/{task_id}/attachments/{file_id}", headers=headers)


# ---------- create with file_ids ----------

def test_create_with_file_ids_attaches_in_order(client):
    alice, bob, _, rid = _setup(client)
    f1, f2 = _file(client, bob, rid, "a.txt"), _file(client, bob, rid, "b.txt")
    t = _task(client, bob, rid, file_ids=[f2, f1, f2])  # duplicates are ignored
    assert [a["file_id"] for a in t["attachments"]] == [f2, f1]
    assert t["attachments"][0] == {"file_id": f2, "name": "b.txt", "size": 6}
    assert _task(client, bob, rid)["attachments"] == []


def test_create_with_a_bad_file_id_is_422_and_creates_nothing(client):
    alice, bob, _, rid = _setup(client)
    other = signup(client, "o@example.com", "Olive")
    other_room = make_room(client, other, "Other")["id"]
    foreign = _file(client, other, other_room)
    mine = _file(client, bob, rid)
    for ids in ([99999], [foreign], [mine, foreign], [mine, 99999]):
        r = client.post(f"/rooms/{rid}/tasks", json={"title": "x", "type": "quiz", "due_at": DUE, "file_ids": ids}, headers=bob)
        assert r.status_code == 422 and r.json()["detail"] == "One of the files was not found in this room", ids
    with SessionLocal() as db:
        assert db.query(TaskFile).count() == 0  # no half-made task or links


def test_create_with_more_than_five_or_wrong_type_is_422(client):
    alice, bob, _, rid = _setup(client)
    ids = [_file(client, bob, rid, f"f{i}.txt") for i in range(6)]
    for payload in (ids, "abc", [1.5], ["x"]):
        r = client.post(f"/rooms/{rid}/tasks", json={"title": "x", "type": "quiz", "due_at": DUE, "file_ids": payload}, headers=bob)
        assert r.status_code == 422
    assert len(_task(client, bob, rid, file_ids=ids[:5])["attachments"]) == 5
    assert _task(client, bob, rid, file_ids=[])["attachments"] == []
    assert _task(client, bob, rid, file_ids=None)["attachments"] == []


# ---------- PUT / DELETE ----------

def test_attach_and_unlink(client):
    alice, bob, _, rid = _setup(client)
    f = _file(client, bob, rid)
    t = _task(client, bob, rid)
    r = _put(client, bob, t["id"], f)
    assert r.status_code == 200 and [a["file_id"] for a in r.json()["attachments"]] == [f]
    assert len(_put(client, bob, t["id"], f).json()["attachments"]) == 1  # twice is fine
    assert _put(client, alice, t["id"], f).status_code == 200  # an admin may too
    assert _del(client, bob, t["id"], f).status_code == 204
    assert _del(client, bob, t["id"], f).status_code == 204  # not linked: still fine
    assert client.get(f"/rooms/{rid}/files", headers=bob).json()[0]["id"] == f  # the file itself stays


def test_attaching_is_not_an_edit(client):
    alice, bob, _, rid = _setup(client)
    f = _file(client, bob, rid)
    t = _task(client, alice, rid)  # Alice is the only admin: auto-approved
    assert t["status"] == "approved"
    r = _put(client, alice, t["id"], f).json()
    assert r["edited_by_name"] is None and r["edited_at"] is None


def test_the_task_card_data_shows_attachments_everywhere(client):
    alice, bob, carol, rid = _setup(client)
    f = _file(client, bob, rid, "guide.txt")
    t = _task(client, alice, rid, file_ids=[f])  # approved
    week = client.get(f"/rooms/{rid}/tasks", params={"week_start": "2030-01-13"}, headers=carol).json()
    assert [a["name"] for a in week[0]["attachments"]] == ["guide.txt"]
    month = client.get(f"/rooms/{rid}/calendar", params={"month": "2030-01"}, headers=carol).json()
    assert month[0]["attachments"][0]["file_id"] == f
    assert "data" not in str(week[0]["attachments"]) and set(week[0]["attachments"][0]) == {"file_id", "name", "size"}


def test_only_creator_or_admin_may_change(client):
    alice, bob, carol, rid = _setup(client)
    f = _file(client, bob, rid)
    t = _task(client, bob, rid)
    assert _put(client, carol, t["id"], f).status_code == 403
    _put(client, bob, t["id"], f)
    assert _del(client, carol, t["id"], f).status_code == 403


def test_rejected_task_is_closed(client):
    alice, bob, _, rid = _setup(client)
    f = _file(client, bob, rid)
    t = _task(client, bob, rid)
    # make Alice reject it: she is the only admin, so Bob's task is pending and she can reject
    assert client.post(f"/tasks/{t['id']}/reject", headers=alice).status_code == 200
    assert _put(client, bob, t["id"], f).status_code == 403
    assert _put(client, alice, t["id"], f).status_code == 403
    assert _del(client, alice, t["id"], f).status_code == 403


def test_non_member_and_missing_task_get_the_same_404(client):
    alice, bob, _, rid = _setup(client)
    outsider = signup(client, "x@example.com", "Xena")
    f = _file(client, bob, rid)
    t = _task(client, bob, rid)
    a = _put(client, outsider, t["id"], f)
    b = _put(client, outsider, 99999, f)
    assert a.status_code == b.status_code == 404 and a.json() == b.json()
    c, d = _del(client, outsider, t["id"], f), _del(client, outsider, 99999, f)
    assert c.status_code == d.status_code == 404 and c.json() == d.json()


def test_file_of_another_room_or_missing_gives_the_same_404(client):
    alice, bob, _, rid = _setup(client)
    other = signup(client, "o@example.com", "Olive")
    foreign = _file(client, other, make_room(client, other, "Other")["id"])
    t = _task(client, bob, rid)
    a, b = _put(client, bob, t["id"], foreign), _put(client, bob, t["id"], 99999)
    assert a.status_code == b.status_code == 404
    assert a.json() == b.json() == {"detail": "File not found"}


def test_at_most_five_notes(client):
    alice, bob, _, rid = _setup(client)
    ids = [_file(client, bob, rid, f"f{i}.txt") for i in range(6)]
    t = _task(client, bob, rid)
    for fid in ids[:5]:
        assert _put(client, bob, t["id"], fid).status_code == 200
    r = _put(client, bob, t["id"], ids[5])
    assert r.status_code == 409 and r.json()["detail"] == "A task can have at most 5 notes"
    assert _put(client, bob, t["id"], ids[0]).status_code == 200  # already linked: still fine at the limit
    _del(client, bob, t["id"], ids[0])
    assert _put(client, bob, t["id"], ids[5]).status_code == 200


def test_needs_login(client):
    assert client.put("/tasks/1/attachments/1").status_code == 401
    assert client.delete("/tasks/1/attachments/1").status_code == 401


def test_attach_is_rate_limited(client, monkeypatch):
    alice, bob, _, rid = _setup(client)
    f = _file(client, bob, rid)
    t = _task(client, bob, rid)
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    codes = [_put(client, bob, t["id"], f).status_code for _ in range(61)]
    ratelimit.reset()
    assert codes[:60] == [200] * 60 and codes[60] == 429


# ---------- cleanup ----------

def test_deleting_the_task_or_the_file_removes_links_only(client):
    alice, bob, _, rid = _setup(client)
    f1, f2 = _file(client, bob, rid, "a.txt"), _file(client, bob, rid, "b.txt")
    t1, t2 = _task(client, bob, rid, "T1", file_ids=[f1, f2]), _task(client, bob, rid, "T2", file_ids=[f1])
    assert client.delete(f"/tasks/{t1['id']}", headers=bob).status_code == 204
    with SessionLocal() as db:
        assert db.query(TaskFile).filter(TaskFile.task_id == t1["id"]).count() == 0
        assert db.query(TaskFile).count() == 1
    assert client.delete(f"/files/{f1}", headers=bob).status_code == 204
    with SessionLocal() as db:
        assert db.query(TaskFile).count() == 0
    # the task itself stays
    assert client.patch(f"/tasks/{t2['id']}", json={"note": "hi"}, headers=bob).status_code == 200


# ---------- used_in on the Notes page ----------

def test_used_in_lists_only_approved_tasks_and_counts_them(client):
    alice, bob, carol, rid = _setup(client)
    f = _file(client, bob, rid)
    lone = _file(client, bob, rid, "lone.txt")
    for i in range(7):  # admin: auto-approved
        _task(client, alice, rid, f"A{i}", file_ids=[f])
    pending = _task(client, bob, rid, "Pending one", file_ids=[f])
    rejected = _task(client, bob, rid, "Rejected one", file_ids=[f])
    client.post(f"/tasks/{rejected['id']}/reject", headers=alice)
    files = {x["id"]: x for x in client.get(f"/rooms/{rid}/files", headers=carol).json()}
    assert files[lone]["used_in"] == [] and files[lone]["used_in_count"] == 0
    assert files[f]["used_in_count"] == 7 and len(files[f]["used_in"]) == 5
    titles = {u["title"] for u in files[f]["used_in"]}
    assert "Pending one" not in titles and "Rejected one" not in titles
    assert set(files[f]["used_in"][0]) == {"task_id", "title"}
    client.post(f"/tasks/{pending['id']}/approve", headers=alice)  # once approved it counts
    files = {x["id"]: x for x in client.get(f"/rooms/{rid}/files", headers=carol).json()}
    assert files[f]["used_in_count"] == 8


def test_used_in_is_member_only_like_the_file_list(client):
    alice, bob, _, rid = _setup(client)
    outsider = signup(client, "x@example.com", "Xena")
    f = _file(client, bob, rid)
    _task(client, alice, rid, file_ids=[f])
    assert client.get(f"/rooms/{rid}/files", headers=outsider).status_code == 403

from datetime import datetime, timedelta, timezone

import pytest

from app.routers import tasks as tasks_router

from .conftest import join_room, make_room, signup

MANILA = timezone(timedelta(hours=8))


@pytest.fixture(autouse=True)
def rule_on(monkeypatch):
    monkeypatch.setattr(tasks_router, "ALLOW_PAST_DUE", False)


def _setup(client):
    alice = signup(client)  # creator and only admin
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _iso(delta):
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _post(client, rid, headers, due_at, all_day=False):
    return client.post(
        f"/rooms/{rid}/tasks",
        json={"title": "T", "type": "quiz", "due_at": due_at, "all_day": all_day},
        headers=headers,
    )


def test_past_due_date_is_422_with_a_clear_message(client):
    alice, bob, rid = _setup(client)
    r = _post(client, rid, alice, _iso(timedelta(days=-1)))
    assert r.status_code == 422
    assert r.json()["detail"] == "due_at must be in the future"


def test_just_passed_is_422(client):
    alice, bob, rid = _setup(client)
    assert _post(client, rid, alice, _iso(timedelta(seconds=-5))).status_code == 422


def test_future_due_date_works(client):
    alice, bob, rid = _setup(client)
    assert _post(client, rid, alice, _iso(timedelta(days=2))).status_code == 201
    assert _post(client, rid, bob, _iso(timedelta(hours=1))).status_code == 201


def test_all_day_today_works(client):
    alice, bob, rid = _setup(client)
    today = datetime.now(MANILA).date()
    end_of_today = datetime(today.year, today.month, today.day, 23, 59, tzinfo=MANILA)
    if end_of_today <= datetime.now(timezone.utc):  # only in the last minute of the Manila day
        pytest.skip("too close to midnight in Manila")
    r = _post(client, rid, alice, end_of_today.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), all_day=True)
    assert r.status_code == 201


def test_patch_into_the_past_is_422(client):
    alice, bob, rid = _setup(client)
    tid = _post(client, rid, bob, _iso(timedelta(days=2))).json()["id"]
    r = client.patch(f"/tasks/{tid}", json={"due_at": _iso(timedelta(days=-1))}, headers=bob)
    assert r.status_code == 422
    assert r.json()["detail"] == "due_at must be in the future"
    ok = client.patch(f"/tasks/{tid}", json={"due_at": _iso(timedelta(days=3))}, headers=bob)
    assert ok.status_code == 200


def test_old_pending_task_can_still_be_edited_and_approved(client, monkeypatch):
    alice, bob, rid = _setup(client)
    monkeypatch.setattr(tasks_router, "ALLOW_PAST_DUE", True)  # make a task that is already overdue
    tid = _post(client, rid, bob, _iso(timedelta(days=-3))).json()["id"]
    monkeypatch.setattr(tasks_router, "ALLOW_PAST_DUE", False)
    # changing only the title is fine, the old date is not touched
    r = client.patch(f"/tasks/{tid}", json={"title": "Renamed"}, headers=bob)
    assert r.status_code == 200 and r.json()["title"] == "Renamed"
    # an admin can still decide it
    assert client.post(f"/tasks/{tid}/approve", headers=alice).status_code == 200
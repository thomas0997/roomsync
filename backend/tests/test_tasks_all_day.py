from .conftest import join_room, make_room, signup

ALL_DAY = "2099-06-01T15:59:00Z"   # 23:59 in Manila, the end of the day
OTHER = "2099-06-01T03:00:00Z"


def _setup(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _post(client, rid, headers, due_at, all_day):
    return client.post(
        f"/rooms/{rid}/tasks",
        json={"title": "T", "type": "quiz", "due_at": due_at, "all_day": all_day},
        headers=headers,
    )


def _patch(client, task_id, headers, body):
    return client.patch(f"/tasks/{task_id}", json=body, headers=headers)


def test_create_all_day_with_the_standard_time(client):
    alice, bob, rid = _setup(client)
    r = _post(client, rid, alice, ALL_DAY, True)
    assert r.status_code == 201, r.text
    assert r.json()["all_day"] is True


def test_manila_offset_form_of_the_standard_time_is_fine(client):
    alice, bob, rid = _setup(client)
    assert _post(client, rid, alice, "2099-06-01T23:59:00+08:00", True).status_code == 201


def test_create_all_day_with_another_time_is_422(client):
    alice, bob, rid = _setup(client)
    assert _post(client, rid, alice, OTHER, True).status_code == 422
    assert _post(client, rid, alice, "2099-06-01T15:59:30Z", True).status_code == 422
    assert _post(client, rid, alice, "2099-06-01T16:00:00Z", True).status_code == 422


def test_a_timed_task_can_use_any_time(client):
    alice, bob, rid = _setup(client)
    assert _post(client, rid, alice, OTHER, False).status_code == 201
    assert _post(client, rid, alice, ALL_DAY, False).status_code == 201  # same time but not all-day: fine


def test_patch_checks_the_final_combination(client):
    alice, bob, rid = _setup(client)
    timed = _post(client, rid, bob, OTHER, False).json()
    allday = _post(client, rid, bob, ALL_DAY, True).json()
    # switching a timed task to all-day without fixing its time is refused
    assert _patch(client, timed["id"], bob, {"all_day": True}).status_code == 422
    # ...but fine when the standard time is sent with it
    assert _patch(client, timed["id"], bob, {"all_day": True, "due_at": ALL_DAY}).status_code == 200
    # moving an all-day task to a non-standard time is refused, unless all_day is turned off
    assert _patch(client, allday["id"], bob, {"due_at": OTHER}).status_code == 422
    r = _patch(client, allday["id"], bob, {"due_at": OTHER, "all_day": False})
    assert r.status_code == 200 and r.json()["all_day"] is False
    # a change that touches neither field is not affected
    assert _patch(client, allday["id"], bob, {"title": "New title"}).status_code == 200
from .conftest import join_room, make_room, signup

FUTURE = "2099-06-01T10:00:00Z"


def _setup(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _add(client, rid, headers, title, due_at=FUTURE, type_="quiz", subject=None):
    body = {"title": title, "type": type_, "due_at": due_at}
    if subject:
        body["subject"] = subject
    r = client.post(f"/rooms/{rid}/tasks", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _search(client, rid, headers, **params):
    return client.get(f"/rooms/{rid}/tasks/search", params=params, headers=headers)


def _titles(r):
    assert r.status_code == 200, r.text
    return [t["title"] for t in r.json()]


def test_matches_title_subject_and_type_ignoring_case(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "Linked List Activity", type_="activity")
    _add(client, rid, alice, "Midterm", type_="exam", subject="6DSAL")
    assert _titles(_search(client, rid, bob, q="linked")) == ["Linked List Activity"]
    assert _titles(_search(client, rid, bob, q="6dsal")) == ["Midterm"]
    assert _titles(_search(client, rid, bob, q="EXAM")) == ["Midterm"]
    assert _titles(_search(client, rid, bob, q="nothing like this")) == []


def test_only_approved_tasks_of_this_room(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "Approved quiz")
    pending = _add(client, rid, bob, "Pending quiz")
    rejected = _add(client, rid, bob, "Rejected quiz")
    client.post(f"/tasks/{rejected['id']}/reject", headers=alice)
    assert pending["status"] == "pending"
    assert _titles(_search(client, rid, bob, q="quiz")) == ["Approved quiz"]
    other = make_room(client, alice, "Other")
    _add(client, other["id"], alice, "Other room quiz")
    assert _titles(_search(client, rid, alice, q="quiz")) == ["Approved quiz"]


def test_upcoming_first_then_past_most_recent_first(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "quiz old", "2019-01-01T10:00:00Z")
    _add(client, rid, alice, "quiz recent", "2021-01-01T10:00:00Z")
    _add(client, rid, alice, "quiz later", "2099-09-01T10:00:00Z")
    _add(client, rid, alice, "quiz soon", "2099-03-01T10:00:00Z")
    assert _titles(_search(client, rid, bob, q="quiz")) == ["quiz soon", "quiz later", "quiz recent", "quiz old"]


def test_limit_counts_upcoming_before_past(client):
    alice, bob, rid = _setup(client)
    for i in range(3):
        _add(client, rid, alice, f"quiz past {i}", f"2020-01-0{i + 1}T10:00:00Z")
    _add(client, rid, alice, "quiz future", FUTURE)
    assert _titles(_search(client, rid, bob, q="quiz", limit=2)) == ["quiz future", "quiz past 2"]
    assert _search(client, rid, bob, q="quiz", limit=0).status_code == 422
    assert _search(client, rid, bob, q="quiz", limit=101).status_code == 422


def test_type_filter(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "Study quiz", type_="quiz")
    _add(client, rid, alice, "Study exam", type_="exam")
    assert _titles(_search(client, rid, bob, q="study", type="exam")) == ["Study exam"]
    assert sorted(_titles(_search(client, rid, bob, q="study"))) == ["Study exam", "Study quiz"]


def test_percent_and_underscore_are_not_wildcards(client):
    alice, bob, rid = _setup(client)
    _add(client, rid, alice, "Read 100% of it")
    _add(client, rid, alice, "Plain title")
    _add(client, rid, alice, "snake_case thing")
    assert _titles(_search(client, rid, bob, q="%")) == ["Read 100% of it"]
    assert _titles(_search(client, rid, bob, q="_")) == ["snake_case thing"]


def test_done_flag_is_mine_and_removed_tasks_still_found(client):
    alice, bob, rid = _setup(client)
    t = _add(client, rid, alice, "Linked quiz")
    client.put(f"/tasks/{t['id']}/done", headers=bob)
    client.put(f"/tasks/{t['id']}/hidden", headers=bob)
    assert _search(client, rid, bob, q="linked").json()[0]["done"] is True
    assert _search(client, rid, alice, q="linked").json()[0]["done"] is False


def test_bad_query_non_member_and_no_token(client):
    alice, bob, rid = _setup(client)
    carol = signup(client, "c@example.com", "Carol")
    assert _search(client, rid, bob).status_code == 422
    assert _search(client, rid, bob, q="").status_code == 422
    assert _search(client, rid, bob, q="   ").status_code == 422
    assert _search(client, rid, bob, q="x" * 51).status_code == 422
    assert _search(client, rid, carol, q="quiz").status_code == 403
    assert client.get(f"/rooms/{rid}/tasks/search", params={"q": "quiz"}).status_code == 401

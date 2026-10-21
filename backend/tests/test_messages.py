from .conftest import join_room, make_room, signup


def _setup(client):
    alice = signup(client)  # room creator, so an admin
    bob = signup(client, "b@example.com", "Bob")
    carol = signup(client, "c@example.com", "Carol")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    join_room(client, carol, room["invite_code"])
    return alice, bob, carol, room


def _post(client, rid, headers, body, **extra):
    r = client.post(f"/rooms/{rid}/messages", json={"body": body, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _list(client, rid, headers, **params):
    return client.get(f"/rooms/{rid}/messages", params=params, headers=headers)


def _bodies(response):
    assert response.status_code == 200, response.text
    return [m["body"] for m in response.json()]


# ---------- POST and GET ----------

def test_member_posts_and_everyone_reads(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    m = _post(client, rid, bob, "hello")
    assert m["body"] == "hello"
    assert m["author_name"] == "Bob"
    assert m["room_id"] == rid
    assert m["reply_to_id"] is None and m["reply_to"] is None
    assert m["created_at"].endswith("Z")
    assert _bodies(_list(client, rid, carol)) == ["hello"]


def test_list_is_oldest_first(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    _post(client, rid, alice, "first")
    _post(client, rid, bob, "second")
    _post(client, rid, carol, "third")
    assert _bodies(_list(client, rid, bob)) == ["first", "second", "third"]


def test_limit_returns_latest_page_and_before_id_pages_back(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    ids = [_post(client, rid, bob, f"m{i}")["id"] for i in range(1, 6)]
    assert _bodies(_list(client, rid, alice, limit=2)) == ["m4", "m5"]
    assert _bodies(_list(client, rid, alice, limit=2, before_id=ids[3])) == ["m2", "m3"]
    assert _bodies(_list(client, rid, alice, limit=2, before_id=ids[1])) == ["m1"]
    assert _list(client, rid, alice, limit=2, before_id=ids[0]).json() == []
    assert len(_list(client, rid, alice).json()) == 5  # the default limit is 50


def test_unknown_or_other_room_before_id_returns_empty_list(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    _post(client, rid, bob, "mine")
    other = make_room(client, alice, name="OTHER")
    other_message = _post(client, other["id"], alice, "elsewhere")
    assert _list(client, rid, alice, before_id=9999).json() == []
    assert _list(client, rid, alice, before_id=other_message["id"]).json() == []


def test_body_is_trimmed_and_length_checked(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    url = f"/rooms/{rid}/messages"
    assert _post(client, rid, bob, "  hi there  ")["body"] == "hi there"
    assert _post(client, rid, bob, "x" * 2000)["body"] == "x" * 2000
    for bad in ("", "   ", "x" * 2001):
        assert client.post(url, json={"body": bad}, headers=bob).status_code == 422, bad[:10]
    assert client.post(url, json={}, headers=bob).status_code == 422
    assert client.post(url, json={"body": None}, headers=bob).status_code == 422


def test_unknown_fields_get_422(client):
    alice, bob, carol, room = _setup(client)
    url = f"/rooms/{room['id']}/messages"
    for extra in ({"author_id": 1}, {"room_id": 5}, {"created_at": "2020-01-01T00:00:00Z"}):
        r = client.post(url, json={"body": "hi", **extra}, headers=bob)
        assert r.status_code == 422, extra


def test_reply_shows_reply_to_with_80_character_snippet(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    parent = _post(client, rid, alice, "a" * 200)
    reply = _post(client, rid, bob, "I agree", reply_to_id=parent["id"])
    assert reply["reply_to_id"] == parent["id"]
    assert reply["reply_to"] == {"author_name": "Alice", "snippet": "a" * 80}
    listed = _list(client, rid, carol).json()
    assert listed[0]["reply_to"] is None
    assert listed[1]["reply_to"] == {"author_name": "Alice", "snippet": "a" * 80}
    short = _post(client, rid, carol, "short one")
    reply2 = _post(client, rid, bob, "ok", reply_to_id=short["id"])
    assert reply2["reply_to"]["snippet"] == "short one"


def test_reply_to_must_be_in_the_same_room(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    other = make_room(client, alice, name="OTHER")
    elsewhere = _post(client, other["id"], alice, "elsewhere")
    url = f"/rooms/{rid}/messages"
    for bad_id in (elsewhere["id"], 9999, 0, -1):
        r = client.post(url, json={"body": "reply", "reply_to_id": bad_id}, headers=bob)
        assert r.status_code == 422, bad_id
    assert _list(client, rid, alice).json() == []  # nothing was saved


def test_bad_list_params_get_422(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    for params in ({"limit": 0}, {"limit": 101}, {"limit": "abc"},
                   {"before_id": 0}, {"before_id": -1}, {"before_id": "abc"}):
        assert _list(client, rid, alice, **params).status_code == 422, params
    assert _list(client, rid, alice, limit=1).status_code == 200
    assert _list(client, rid, alice, limit=100).status_code == 200


def test_other_rooms_messages_are_hidden(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    other = make_room(client, alice, name="OTHER")
    _post(client, other["id"], alice, "elsewhere")
    _post(client, rid, bob, "mine")
    assert _bodies(_list(client, rid, alice)) == ["mine"]


def test_non_member_gets_403_on_list_and_post(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    dave = signup(client, "d@example.com", "Dave")  # not in the room
    assert _list(client, rid, dave).status_code == 403
    assert client.post(f"/rooms/{rid}/messages", json={"body": "hi"}, headers=dave).status_code == 403


def test_no_token_gets_401(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    m = _post(client, rid, bob, "hello")
    assert client.get(f"/rooms/{rid}/messages").status_code == 401
    assert client.post(f"/rooms/{rid}/messages", json={"body": "hi"}).status_code == 401
    assert client.delete(f"/messages/{m['id']}").status_code == 401


# ---------- DELETE ----------

def test_author_can_delete_own_message(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    m = _post(client, rid, bob, "oops")
    assert client.delete(f"/messages/{m['id']}", headers=bob).status_code == 204
    assert _list(client, rid, alice).json() == []
    assert client.delete(f"/messages/{m['id']}", headers=bob).status_code == 404  # it is gone


def test_nobody_else_can_delete_not_even_an_admin(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    m = _post(client, rid, bob, "mine")
    assert client.delete(f"/messages/{m['id']}", headers=alice).status_code == 403  # the room admin
    assert client.delete(f"/messages/{m['id']}", headers=carol).status_code == 403  # another member
    assert _bodies(_list(client, rid, alice)) == ["mine"]


def test_delete_by_non_member_or_missing_message_gets_404(client):
    alice, bob, carol, room = _setup(client)
    dave = signup(client, "d@example.com", "Dave")  # not in the room
    m = _post(client, room["id"], bob, "mine")
    assert client.delete(f"/messages/{m['id']}", headers=dave).status_code == 404
    assert client.delete("/messages/9999", headers=alice).status_code == 404


def test_deleting_a_replied_to_message_keeps_the_replies(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    parent = _post(client, rid, bob, "parent")
    _post(client, rid, carol, "reply", reply_to_id=parent["id"])
    assert client.delete(f"/messages/{parent['id']}", headers=bob).status_code == 204
    listed = _list(client, rid, alice).json()
    assert [x["body"] for x in listed] == ["reply"]
    assert listed[0]["reply_to_id"] is None
    assert listed[0]["reply_to"] is None


# ---------- deleted users ----------

def test_deleted_users_show_as_deleted_user(client):
    alice, bob, carol, room = _setup(client)
    rid = room["id"]
    _post(client, rid, bob, "from bob")
    assert client.delete("/users/me", headers=bob).status_code == 204  # Bob deletes his account
    listed = _list(client, rid, alice).json()
    assert listed[0]["body"] == "from bob"  # his message stays
    assert listed[0]["author_name"] == "Deleted user"
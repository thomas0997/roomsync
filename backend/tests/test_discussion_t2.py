"""Discussion T2: @mentions, clip attachments, unread counts, "seen by". See docs/api-contract.md."""
from .conftest import join_room, make_room, signup


def _setup(client):
    alice = signup(client, "a@example.com", "Alice")  # creates the room: admin
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room


def _post(client, rid, headers, body, **extra):
    r = client.post(f"/rooms/{rid}/messages", json={"body": body, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _file(client, headers, rid, name="n.txt"):
    r = client.post(f"/rooms/{rid}/files", params={"name": name}, content=b"hello\n",
                     headers={**headers, "Content-Type": "application/octet-stream"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------- @mentions ----------

def test_mentions_match_current_member_full_name_on_word_boundary(client):
    alice = signup(client, "a@example.com", "Alice")
    bob = signup(client, "b@example.com", "Bob")
    carol = signup(client, "c@example.com", "Carol Danvers")  # name has a space
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    join_room(client, carol, room["invite_code"])
    rid = room["id"]

    m1 = _post(client, rid, alice, "@Bob check this out")
    assert m1["mentions"] == [2]  # Bob's user id (second signup)

    m2 = _post(client, rid, alice, "Hey @Carol Danvers, look at this")
    assert m2["mentions"] == [3]

    m3 = _post(client, rid, alice, "@Bobby isn't a member, so no match")
    assert m3["mentions"] == []

    m4 = _post(client, rid, alice, "email bob@example.com isn't a mention either")
    assert m4["mentions"] == []  # case-sensitive, no leading @Bob

    m5 = _post(client, rid, alice, "@Bob and @Carol Danvers in one message")
    assert sorted(m5["mentions"]) == [2, 3]


def test_mentions_are_recomputed_live_not_stored(client):
    alice, bob, room = _setup(client)
    rid = room["id"]
    msg = _post(client, rid, alice, "@Bob hi")
    assert msg["mentions"] == [bob_id(client, bob)]

    # Bob renames himself; the OLD message's mentions should now reflect the new name, since
    # mentions are computed fresh on every read against the current member list, never stored.
    r = client.patch("/users/me", json={"name": "Robert"}, headers=bob)
    assert r.status_code == 200, r.text

    listed = client.get(f"/rooms/{rid}/messages", headers=alice).json()
    assert listed[0]["mentions"] == []  # "@Bob" no longer matches anyone


def bob_id(client, bob_headers):
    return client.get("/users/me", headers=bob_headers).json()["id"]


# ---------- clip attachments ----------

def test_attach_a_room_file_by_the_clip(client):
    alice, bob, room = _setup(client)
    rid = room["id"]
    fid = _file(client, alice, rid, "notes.txt")

    msg = _post(client, rid, bob, "see attached", file_ids=[fid])
    assert msg["attachments"] == [{"file_id": fid, "name": "notes.txt", "size": 6}]

    listed = client.get(f"/rooms/{rid}/messages", headers=alice).json()
    assert listed[0]["attachments"][0]["file_id"] == fid


def test_attachment_must_be_a_file_of_this_room(client):
    alice, bob, room = _setup(client)
    rid = room["id"]
    other = make_room(client, alice, name="OTHER")
    other_fid = _file(client, alice, other["id"], "elsewhere.txt")

    r = client.post(f"/rooms/{rid}/messages", json={"body": "hi", "file_ids": [other_fid]}, headers=bob)
    assert r.status_code == 422
    assert r.json()["detail"] == "One of the files was not found in this room"
    assert client.get(f"/rooms/{rid}/messages", headers=alice).json() == []  # nothing was saved


def test_attachment_missing_file_id_gives_422(client):
    alice, bob, room = _setup(client)
    rid = room["id"]
    r = client.post(f"/rooms/{rid}/messages", json={"body": "hi", "file_ids": [9999]}, headers=bob)
    assert r.status_code == 422


def test_at_most_five_attachments(client):
    alice, bob, room = _setup(client)
    rid = room["id"]
    fids = [_file(client, alice, rid, f"n{i}.txt") for i in range(6)]
    r = client.post(f"/rooms/{rid}/messages", json={"body": "hi", "file_ids": fids}, headers=bob)
    assert r.status_code == 422  # 6 is over the cap

    msg = _post(client, rid, bob, "ok now", file_ids=fids[:5])
    assert len(msg["attachments"]) == 5


def test_duplicate_file_ids_dedupe(client):
    alice, bob, room = _setup(client)
    rid = room["id"]
    fid = _file(client, alice, rid)
    msg = _post(client, rid, bob, "hi", file_ids=[fid, fid, fid])
    assert len(msg["attachments"]) == 1


# ---------- unread counts ----------

def test_unread_count_ignores_history_before_you_joined(client):
    alice = signup(client, "a@example.com", "Alice")
    room = make_room(client, alice)
    rid = room["id"]
    _post(client, rid, alice, "before bob joined")

    bob = signup(client, "b@example.com", "Bob")
    join_room(client, bob, room["invite_code"])
    assert client.get(f"/rooms/{rid}/messages/unread-count", headers=bob).json() == {"count": 0}


def test_unread_count_excludes_own_messages_and_read_resets_it(client):
    alice, bob, room = _setup(client)
    rid = room["id"]
    _post(client, rid, bob, "my own message")  # should never count as unread for bob himself
    assert client.get(f"/rooms/{rid}/messages/unread-count", headers=bob).json() == {"count": 0}

    _post(client, rid, alice, "one")
    _post(client, rid, alice, "two")
    assert client.get(f"/rooms/{rid}/messages/unread-count", headers=bob).json() == {"count": 2}

    assert client.post(f"/rooms/{rid}/messages/read", headers=bob).status_code == 204
    assert client.get(f"/rooms/{rid}/messages/unread-count", headers=bob).json() == {"count": 0}

    _post(client, rid, alice, "three")
    assert client.get(f"/rooms/{rid}/messages/unread-count", headers=bob).json() == {"count": 1}


def test_unread_count_non_member_403_no_token_401(client):
    alice, bob, room = _setup(client)
    rid = room["id"]
    dave = signup(client, "d@example.com", "Dave")
    assert client.get(f"/rooms/{rid}/messages/unread-count", headers=dave).status_code == 403
    assert client.post(f"/rooms/{rid}/messages/read", headers=dave).status_code == 403
    assert client.get(f"/rooms/{rid}/messages/unread-count").status_code == 401
    assert client.post(f"/rooms/{rid}/messages/read").status_code == 401


# ---------- seen by ----------

def test_seen_by_empty_room_has_no_messages_yet(client):
    alice, bob, room = _setup(client)
    assert client.get(f"/rooms/{room['id']}/messages/seen", headers=alice).json() == []


def test_seen_by_excludes_members_who_have_not_caught_up(client):
    alice, bob, room = _setup(client)
    rid = room["id"]
    _post(client, rid, alice, "hi")

    # Bob hasn't acknowledged reading anything yet: no marker row, so he's not "seen" yet.
    assert client.get(f"/rooms/{rid}/messages/seen", headers=alice).json() == []

    assert client.post(f"/rooms/{rid}/messages/read", headers=bob).status_code == 204
    seen = client.get(f"/rooms/{rid}/messages/seen", headers=alice).json()
    assert seen == [{"user_id": bob_id(client, bob), "name": "Bob"}]

    # seen-by excludes the caller themselves even if they're caught up
    assert client.post(f"/rooms/{rid}/messages/read", headers=alice).status_code == 204
    assert client.get(f"/rooms/{rid}/messages/seen", headers=alice).json() == seen


def test_seen_by_non_member_403(client):
    alice, bob, room = _setup(client)
    dave = signup(client, "d@example.com", "Dave")
    assert client.get(f"/rooms/{room['id']}/messages/seen", headers=dave).status_code == 403

from .conftest import join_room, make_room, signup


def _setup(client):
    """Alice creates the room (creator + admin). Bob and Carol join as members."""
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    carol = signup(client, "c@example.com", "Carol")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    join_room(client, carol, room["invite_code"])
    return alice, bob, carol, room["id"]


def _ids(client, headers, rid):
    return {m["name"]: m["user_id"] for m in client.get(f"/rooms/{rid}/members", headers=headers).json()}


def _set(client, headers, rid, uid, role):
    return client.post(f"/rooms/{rid}/members/{uid}/role", json={"role": role}, headers=headers)


def test_creator_can_promote_member(client):
    alice, bob, carol, rid = _setup(client)
    ids = _ids(client, alice, rid)
    r = _set(client, alice, rid, ids["Bob"], "admin")
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin" and r.json()["name"] == "Bob"
    roles = {m["name"]: m["role"] for m in client.get(f"/rooms/{rid}/members", headers=alice).json()}
    assert roles == {"Alice": "admin", "Bob": "admin", "Carol": "member"}


def test_any_admin_can_promote(client):
    alice, bob, carol, rid = _setup(client)
    ids = _ids(client, alice, rid)
    _set(client, alice, rid, ids["Bob"], "admin")
    r = _set(client, bob, rid, ids["Carol"], "admin")  # Bob is an admin now, not the creator
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_member_cannot_change_roles(client):
    alice, bob, carol, rid = _setup(client)
    ids = _ids(client, alice, rid)
    assert _set(client, bob, rid, ids["Carol"], "admin").status_code == 403
    assert _set(client, bob, rid, ids["Bob"], "admin").status_code == 403  # can't promote self either


def test_non_member_gets_403_and_no_token_gets_401(client):
    alice, bob, carol, rid = _setup(client)
    dave = signup(client, "d@example.com", "Dave")
    ids = _ids(client, alice, rid)
    assert _set(client, dave, rid, ids["Bob"], "admin").status_code == 403
    r = client.post(f"/rooms/{rid}/members/{ids['Bob']}/role", json={"role": "admin"})
    assert r.status_code == 401


def test_unknown_member_gets_404(client):
    alice, bob, carol, rid = _setup(client)
    dave = signup(client, "d@example.com", "Dave")  # exists, but is not in this room
    dave_id = client.get("/auth/me", headers=dave).json()["id"]
    assert _set(client, alice, rid, dave_id, "admin").status_code == 404


def test_only_creator_can_demote(client):
    alice, bob, carol, rid = _setup(client)
    ids = _ids(client, alice, rid)
    _set(client, alice, rid, ids["Bob"], "admin")
    _set(client, alice, rid, ids["Carol"], "admin")
    # Bob is an admin but not the creator: he can't demote Carol
    assert _set(client, bob, rid, ids["Carol"], "member").status_code == 403
    # The creator can
    r = _set(client, alice, rid, ids["Carol"], "member")
    assert r.status_code == 200 and r.json()["role"] == "member"


def test_creator_cannot_be_demoted(client):
    alice, bob, carol, rid = _setup(client)
    ids = _ids(client, alice, rid)
    assert _set(client, alice, rid, ids["Alice"], "member").status_code == 400
    _set(client, alice, rid, ids["Bob"], "admin")
    assert _set(client, bob, rid, ids["Alice"], "member").status_code == 403  # Bob isn't the creator


def test_invalid_role_gets_422(client):
    alice, bob, carol, rid = _setup(client)
    ids = _ids(client, alice, rid)
    assert _set(client, alice, rid, ids["Bob"], "owner").status_code == 422
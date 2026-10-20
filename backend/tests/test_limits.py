"""Room limits: at most MAX_ROOMS_PER_USER rooms per user and MAX_MEMBERS_PER_ROOM members per room (409)."""
from app.routers import rooms as rooms_module

from .conftest import make_room, signup


def test_default_limits():
    assert rooms_module.MAX_ROOMS_PER_USER == 10
    assert rooms_module.MAX_MEMBERS_PER_ROOM == 50


def test_create_blocked_at_room_limit_and_leaving_frees_a_slot(client, monkeypatch):
    monkeypatch.setattr(rooms_module, "MAX_ROOMS_PER_USER", 2)
    a = signup(client)
    first = make_room(client, a, "One")
    make_room(client, a, "Two")
    r = client.post("/rooms", json={"name": "Three"}, headers=a)
    assert r.status_code == 409 and "Room limit reached" in r.json()["detail"]
    assert len(client.get("/rooms", headers=a).json()) == 2
    assert client.post(f"/rooms/{first['id']}/leave", headers=a).status_code == 204
    assert client.post("/rooms", json={"name": "Three"}, headers=a).status_code == 201


def test_join_blocked_at_room_limit_but_rejoining_is_fine(client, monkeypatch):
    monkeypatch.setattr(rooms_module, "MAX_ROOMS_PER_USER", 2)
    owner = signup(client, "owner@example.com", "Owner")
    other = make_room(client, owner, "Other")
    b = signup(client, "b@example.com", "Bob")
    mine1 = make_room(client, b, "B1")
    make_room(client, b, "B2")
    r = client.post("/rooms/join", json={"invite_code": other["invite_code"]}, headers=b)
    assert r.status_code == 409 and "Room limit reached" in r.json()["detail"]
    # a room you are already in is not a new room: allowed even at the limit
    r = client.post("/rooms/join", json={"invite_code": mine1["invite_code"]}, headers=b)
    assert r.status_code == 200


def test_join_blocked_when_room_is_full(client, monkeypatch):
    monkeypatch.setattr(rooms_module, "MAX_MEMBERS_PER_ROOM", 2)
    a = signup(client, "a@example.com", "Alice")
    room = make_room(client, a)
    code = room["invite_code"]
    b = signup(client, "b@example.com", "Bob")
    c = signup(client, "c@example.com", "Cara")
    assert client.post("/rooms/join", json={"invite_code": code}, headers=b).status_code == 200
    r = client.post("/rooms/join", json={"invite_code": code}, headers=c)
    assert r.status_code == 409 and "full" in r.json()["detail"]
    # a member joining again is not a new member
    assert client.post("/rooms/join", json={"invite_code": code}, headers=b).status_code == 200
    # when someone leaves, the next person fits
    assert client.post(f"/rooms/{room['id']}/leave", headers=b).status_code == 204
    assert client.post("/rooms/join", json={"invite_code": code}, headers=c).status_code == 200
    assert len(client.get(f"/rooms/{room['id']}/members", headers=a).json()) == 2


def test_limits_need_login(client):
    assert client.post("/rooms", json={"name": "X"}).status_code == 401
    assert client.post("/rooms/join", json={"invite_code": "ABCD1234"}).status_code == 401
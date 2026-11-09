from .conftest import join_room, make_room, signup


def test_requires_login(client):
    assert client.post("/presence/ping").status_code == 401


def test_ping_marks_online(client):
    a = signup(client, "a@example.com", "Alice")
    b = signup(client, "b@example.com", "Bob")
    room = make_room(client, a)
    join_room(client, b, room["invite_code"])

    # Nobody has pinged yet: both show offline.
    members = client.get(f"/rooms/{room['id']}/members", headers=a).json()
    assert all(m["online"] is False for m in members)

    assert client.post("/presence/ping", headers=b).status_code == 204
    members = client.get(f"/rooms/{room['id']}/members", headers=a).json()
    bob = next(m for m in members if m["name"] == "Bob")
    alice = next(m for m in members if m["name"] == "Alice")
    assert bob["online"] is True
    assert alice["online"] is False


def test_ping_is_per_user(client):
    a = signup(client, "a@example.com", "Alice")
    client.post("/presence/ping", headers=a)
    b = signup(client, "b@example.com", "Bob")
    assert client.get("/users/me", headers=b).status_code == 200  # a second account is unaffected

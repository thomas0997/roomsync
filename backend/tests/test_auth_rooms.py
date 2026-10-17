from .conftest import signup


def test_signup_login_me(client):
    h = signup(client)
    assert client.get("/auth/me", headers=h).json()["email"] == "a@example.com"
    r = client.post("/auth/login", json={"email": "A@example.com", "password": "password123"})
    assert r.status_code == 200


def test_duplicate_and_bad_login(client):
    signup(client)
    r = client.post("/auth/signup", json={"email": "a@example.com", "name": "x", "password": "password123"})
    assert r.status_code == 409
    r = client.post("/auth/login", json={"email": "a@example.com", "password": "wrongpass1"})
    assert r.status_code == 401


def test_weak_password_rejected(client):
    r = client.post("/auth/signup", json={"email": "b@example.com", "name": "B", "password": "short"})
    assert r.status_code == 422


def test_requires_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/rooms").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_room_flow_and_permissions(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    room = client.post("/rooms", json={"name": "CYB201"}, headers=alice).json()
    assert room["role"] == "admin"
    rid = room["id"]

    # Bob is not a member yet: forbidden
    assert client.get(f"/rooms/{rid}/members", headers=bob).status_code == 403

    # Bob joins with the code (case-insensitive), now allowed
    j = client.post("/rooms/join", json={"invite_code": room["invite_code"].lower()}, headers=bob)
    assert j.status_code == 200 and j.json()["role"] == "member"
    assert len(client.get(f"/rooms/{rid}/members", headers=bob).json()) == 2
    assert client.post("/rooms/join", json={"invite_code": "NOPE1234"}, headers=bob).status_code == 404

    # Sole admin can't abandon the room while others remain
    assert client.post(f"/rooms/{rid}/leave", headers=alice).status_code == 400
    assert client.post(f"/rooms/{rid}/leave", headers=bob).status_code == 204
    # Last member leaving deletes the room
    assert client.post(f"/rooms/{rid}/leave", headers=alice).status_code == 204
    assert client.get("/rooms", headers=alice).json() == []

from .conftest import join_room, make_room, signup


# ---- invite code is admin-only ----
def test_admin_sees_invite_code_member_does_not(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    assert room["invite_code"]  # the creator is the admin and sees the code

    joined = join_room(client, bob, room["invite_code"])
    assert joined["role"] == "member"
    assert joined["invite_code"] is None

    mine_alice = client.get("/rooms", headers=alice).json()[0]
    mine_bob = client.get("/rooms", headers=bob).json()[0]
    assert mine_alice["invite_code"] == room["invite_code"]
    assert mine_bob["invite_code"] is None


def test_promoted_member_gets_the_code(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    bob_id = next(m["user_id"] for m in client.get(f"/rooms/{room['id']}/members", headers=alice).json() if m["name"] == "Bob")

    r = client.post(f"/rooms/{room['id']}/members/{bob_id}/role", json={"role": "admin"}, headers=alice)
    assert r.status_code == 200, r.text
    assert client.get("/rooms", headers=bob).json()[0]["invite_code"] == room["invite_code"]


def test_rejoining_does_not_leak_the_code(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    again = join_room(client, bob, room["invite_code"])  # already a member: returns the room
    assert again["invite_code"] is None


def test_no_token_still_401(client):
    assert client.get("/rooms").status_code == 401


# ---- frontend files are re-checked by browsers ----
def test_frontend_files_say_no_cache(client):
    for path in ("/pages/login.html", "/css/styles.css", "/js/rooms.js", "/assets/roomsync_logo.png"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "no-cache", path


def test_unchanged_file_returns_304(client):
    first = client.get("/css/styles.css")
    etag = first.headers["etag"]
    second = client.get("/css/styles.css", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.headers["cache-control"] == "no-cache"


def test_api_responses_are_not_marked_no_cache(client):
    r = client.get("/health")
    assert "cache-control" not in r.headers
"""Viewing another person's profile (GET /users/{id}): room-mates only, no email, same 404 for everyone else."""
import io

from PIL import Image

from .conftest import join_room, make_room, signup


def _id(client, headers):
    return client.get("/users/me", headers=headers).json()["id"]


def _setup(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    carol = signup(client, "c@example.com", "Carol")
    room_a = make_room(client, alice, "CYB201")          # alice + bob
    join_room(client, bob, room_a["invite_code"])
    room_b = make_room(client, bob, "Study Group")       # bob + carol
    join_room(client, carol, room_b["invite_code"])
    return alice, bob, carol, room_a, room_b


def test_a_room_mate_sees_name_status_join_date_and_shared_rooms(client):
    alice, bob, carol, room_a, room_b = _setup(client)
    r = client.get(f"/users/{_id(client, bob)}", headers=alice)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Bob" and body["status"]["kind"] == "working" and body["joined_at"]
    assert body["rooms"] == [{"id": room_a["id"], "name": "CYB201"}]     # only the room THEY share, not "Study Group"
    assert body["avatar_url"] is None


def test_the_email_is_never_included(client):
    alice, bob, *_ = _setup(client)
    body = client.get(f"/users/{_id(client, bob)}", headers=alice).json()
    assert "email" not in body and "b@example.com" not in str(body)


def test_someone_in_none_of_my_rooms_is_a_404(client):
    alice, bob, carol, *_ = _setup(client)
    r = client.get(f"/users/{_id(client, carol)}", headers=alice)      # alice and carol share nothing
    assert r.status_code == 404 and r.json()["detail"] == "User not found"


def test_missing_and_deleted_users_look_exactly_the_same(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    join_room(client, bob, make_room(client, alice)["invite_code"])        # bob is a plain member: he can delete his account
    bob_id = _id(client, bob)
    missing = client.get("/users/999999", headers=alice)
    assert client.delete("/users/me", headers=bob).status_code == 204
    deleted = client.get(f"/users/{bob_id}", headers=alice)
    assert missing.status_code == deleted.status_code == 404 and missing.json() == deleted.json()


def test_my_own_profile_works_even_with_no_rooms(client):
    loner = signup(client, "d@example.com", "Dave")
    body = client.get(f"/users/{_id(client, loner)}", headers=loner).json()
    assert body["name"] == "Dave" and body["rooms"] == []
    assert "email" not in body


def test_users_me_still_returns_my_own_profile_with_email(client):
    alice, *_ = _setup(client)
    assert client.get("/users/me", headers=alice).json()["email"] == "a@example.com"


def test_a_custom_status_is_visible_to_room_mates(client):
    alice, bob, *_ = _setup(client)
    assert client.patch("/users/me", json={"status_kind": "custom", "status_text": "Studying for finals"}, headers=bob).status_code == 200
    status = client.get(f"/users/{_id(client, bob)}", headers=alice).json()["status"]
    assert status == {"kind": "custom", "text": "Studying for finals"}


def test_a_photo_url_shows_up_when_they_have_one(client):
    alice, bob, *_ = _setup(client)
    png = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(png, "PNG")
    up = client.put("/users/me/avatar", content=png.getvalue(), headers={**bob, "Content-Type": "image/png"})
    assert up.status_code == 200
    body = client.get(f"/users/{_id(client, bob)}", headers=alice).json()
    assert body["avatar_url"].startswith(f"/users/{_id(client, bob)}/avatar")


def test_needs_a_login_and_a_numeric_id(client):
    alice, bob, *_ = _setup(client)
    assert client.get(f"/users/{_id(client, bob)}").status_code in (401, 403)
    assert client.get("/users/abc", headers=alice).status_code == 422

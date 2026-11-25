"""Folders (flat, no nesting) for grouping files in a room's Notes, plus public folder share links
(/folders/{id}/share, /public/folders/{token}, /public/folders/{token}/files/{file_id})."""
import pytest

from app import ratelimit

from .conftest import join_room, make_room, signup

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def _setup(client):
    alice = signup(client)  # room creator = admin
    bob = signup(client, "b@example.com", "Bob")  # plain member
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _up(client, headers, rid, name, data):
    r = client.post(f"/rooms/{rid}/files", params={"name": name}, content=data,
                     headers={**headers, "Content-Type": "application/octet-stream"})
    assert r.status_code == 201, r.text
    return r.json()


def _mk_folder(client, headers, rid, name="Handouts"):
    r = client.post(f"/rooms/{rid}/folders", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- creating / listing
def test_any_member_can_create_a_folder(client):
    alice, bob, rid = _setup(client)
    f = _mk_folder(client, bob, rid, "Bob's stuff")  # plain member
    assert f["name"] == "Bob's stuff"
    assert f["file_count"] == 0
    assert f["is_public"] is False


def test_folder_name_is_validated(client):
    alice, _, rid = _setup(client)
    assert client.post(f"/rooms/{rid}/folders", json={"name": "  "}, headers=alice).status_code == 422
    assert client.post(f"/rooms/{rid}/folders", json={"name": "x" * 101}, headers=alice).status_code == 422


def test_non_member_cannot_create_a_folder(client):
    alice, _, rid = _setup(client)
    stranger = signup(client, "stranger@example.com", "Stranger")
    assert client.post(f"/rooms/{rid}/folders", json={"name": "Nope"}, headers=stranger).status_code == 403


def test_list_folders_shows_file_count(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    f = _up(client, alice, rid, "a.pdf", PDF)
    client.patch(f"/files/{f['id']}/move", json={"folder_id": folder["id"]}, headers=alice)

    listed = next(x for x in client.get(f"/rooms/{rid}/folders", headers=alice).json() if x["id"] == folder["id"])
    assert listed["file_count"] == 1


# ---------------------------------------------------------------- renaming / deleting
def test_creator_can_rename_their_folder(client):
    alice, bob, rid = _setup(client)
    folder = _mk_folder(client, bob, rid)
    r = client.patch(f"/folders/{folder['id']}", json={"name": "Renamed"}, headers=bob)
    assert r.status_code == 200 and r.json()["name"] == "Renamed"


def test_plain_member_cannot_rename_someone_elses_folder(client):
    alice, bob, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    assert client.patch(f"/folders/{folder['id']}", json={"name": "Hijacked"}, headers=bob).status_code == 403


def test_admin_can_rename_anyones_folder(client):
    alice, bob, rid = _setup(client)
    folder = _mk_folder(client, bob, rid)
    assert client.patch(f"/folders/{folder['id']}", json={"name": "Admin edit"}, headers=alice).status_code == 200


def test_deleting_a_folder_unfiles_its_files_instead_of_deleting_them(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    f = _up(client, alice, rid, "a.pdf", PDF)
    client.patch(f"/files/{f['id']}/move", json={"folder_id": folder["id"]}, headers=alice)

    assert client.delete(f"/folders/{folder['id']}", headers=alice).status_code == 204

    files = client.get(f"/rooms/{rid}/files", headers=alice).json()
    moved = next(x for x in files if x["id"] == f["id"])
    assert moved["folder_id"] is None  # file survives, just unfiled
    assert client.get(f"/rooms/{rid}/folders", headers=alice).json() == []


def test_plain_member_cannot_delete_someone_elses_folder(client):
    alice, bob, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    assert client.delete(f"/folders/{folder['id']}", headers=bob).status_code == 403


def test_non_member_gets_404_not_403_on_someone_elses_folder(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    stranger = signup(client, "stranger2@example.com", "Stranger2")
    assert client.patch(f"/folders/{folder['id']}", json={"name": "x"}, headers=stranger).status_code == 404
    assert client.delete(f"/folders/{folder['id']}", headers=stranger).status_code == 404


# ---------------------------------------------------------------- moving files
def test_owner_can_move_their_file_into_and_out_of_a_folder(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    f = _up(client, alice, rid, "a.pdf", PDF)

    into = client.patch(f"/files/{f['id']}/move", json={"folder_id": folder["id"]}, headers=alice)
    assert into.status_code == 200 and into.json()["folder_id"] == folder["id"]

    out = client.patch(f"/files/{f['id']}/move", json={"folder_id": None}, headers=alice)
    assert out.status_code == 200 and out.json()["folder_id"] is None


def test_plain_member_cannot_move_someone_elses_file(client):
    alice, bob, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    f = _up(client, alice, rid, "a.pdf", PDF)
    assert client.patch(f"/files/{f['id']}/move", json={"folder_id": folder["id"]}, headers=bob).status_code == 403


def test_cannot_move_a_file_into_a_folder_from_another_room(client):
    alice, _, rid = _setup(client)
    other_room = make_room(client, alice)
    other_folder = _mk_folder(client, alice, other_room["id"])
    f = _up(client, alice, rid, "a.pdf", PDF)
    r = client.patch(f"/files/{f['id']}/move", json={"folder_id": other_folder["id"]}, headers=alice)
    assert r.status_code == 404


def test_filtering_file_list_by_folder_and_unfiled(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    inside = _up(client, alice, rid, "inside.pdf", PDF)
    outside = _up(client, alice, rid, "outside.pdf", PDF)
    client.patch(f"/files/{inside['id']}/move", json={"folder_id": folder["id"]}, headers=alice)

    by_folder = client.get(f"/rooms/{rid}/files?folder_id={folder['id']}", headers=alice).json()
    assert [x["id"] for x in by_folder] == [inside["id"]]

    unfiled = client.get(f"/rooms/{rid}/files?unfiled=true", headers=alice).json()
    assert [x["id"] for x in unfiled] == [outside["id"]]


# ---------------------------------------------------------------- folder sharing: turning it on/off
def test_creator_can_share_their_folder(client):
    alice, bob, rid = _setup(client)
    folder = _mk_folder(client, bob, rid)
    r = client.post(f"/folders/{folder['id']}/share", headers=bob)
    assert r.status_code == 200
    body = r.json()
    assert body["is_public"] is True
    assert body["share_token"] and len(body["share_token"]) >= 20


def test_admin_can_share_someone_elses_folder(client):
    alice, bob, rid = _setup(client)
    folder = _mk_folder(client, bob, rid)
    r = client.post(f"/folders/{folder['id']}/share", headers=alice)
    assert r.status_code == 200 and r.json()["is_public"] is True


def test_plain_member_cannot_share_someone_elses_folder(client):
    alice, bob, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    assert client.post(f"/folders/{folder['id']}/share", headers=bob).status_code == 403


def test_sharing_folder_twice_keeps_the_same_token(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    first = client.post(f"/folders/{folder['id']}/share", headers=alice).json()["share_token"]
    second = client.post(f"/folders/{folder['id']}/share", headers=alice).json()["share_token"]
    assert first == second


def test_turning_off_folder_share_kills_the_old_link(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    token = client.post(f"/folders/{folder['id']}/share", headers=alice).json()["share_token"]
    assert client.get(f"/public/folders/{token}").status_code == 200

    off = client.delete(f"/folders/{folder['id']}/share", headers=alice)
    assert off.status_code == 200
    assert off.json()["is_public"] is False and off.json()["share_token"] is None

    assert client.get(f"/public/folders/{token}").status_code == 404


def test_plain_member_cannot_turn_off_someone_elses_folder_share(client):
    alice, bob, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    client.post(f"/folders/{folder['id']}/share", headers=alice)
    assert client.delete(f"/folders/{folder['id']}/share", headers=bob).status_code == 403


# ---------------------------------------------------------------- the public endpoints themselves
def test_public_folder_listing_needs_no_login(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid, "Shared Stuff")
    f = _up(client, alice, rid, "a.pdf", PDF)
    client.patch(f"/files/{f['id']}/move", json={"folder_id": folder["id"]}, headers=alice)
    token = client.post(f"/folders/{folder['id']}/share", headers=alice).json()["share_token"]

    r = client.get(f"/public/folders/{token}")  # no Authorization header
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Shared Stuff"
    assert [x["name"] for x in body["files"]] == ["a.pdf"]
    assert "share_token" not in body["files"][0]


def test_public_folder_download_needs_no_login(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    f = _up(client, alice, rid, "a.pdf", PDF)
    client.patch(f"/files/{f['id']}/move", json={"folder_id": folder["id"]}, headers=alice)
    token = client.post(f"/folders/{folder['id']}/share", headers=alice).json()["share_token"]

    r = client.get(f"/public/folders/{token}/files/{f['id']}")
    assert r.status_code == 200
    assert r.content == PDF
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_file_moved_out_of_shared_folder_is_no_longer_reachable(client):
    alice, _, rid = _setup(client)
    folder = _mk_folder(client, alice, rid)
    f = _up(client, alice, rid, "a.pdf", PDF)
    client.patch(f"/files/{f['id']}/move", json={"folder_id": folder["id"]}, headers=alice)
    token = client.post(f"/folders/{folder['id']}/share", headers=alice).json()["share_token"]
    assert client.get(f"/public/folders/{token}/files/{f['id']}").status_code == 200

    client.patch(f"/files/{f['id']}/move", json={"folder_id": None}, headers=alice)
    assert client.get(f"/public/folders/{token}/files/{f['id']}").status_code == 404
    # the listing itself also drops it immediately
    assert client.get(f"/public/folders/{token}").json()["files"] == []


def test_sharing_one_folder_does_not_expose_files_in_another_folder(client):
    alice, _, rid = _setup(client)
    shared = _mk_folder(client, alice, rid, "Shared")
    other = _mk_folder(client, alice, rid, "Private")
    a = _up(client, alice, rid, "a.pdf", PDF)
    b = _up(client, alice, rid, "b.pdf", PDF)
    client.patch(f"/files/{a['id']}/move", json={"folder_id": shared["id"]}, headers=alice)
    client.patch(f"/files/{b['id']}/move", json={"folder_id": other["id"]}, headers=alice)
    token = client.post(f"/folders/{shared['id']}/share", headers=alice).json()["share_token"]

    listing = client.get(f"/public/folders/{token}").json()
    assert [x["id"] for x in listing["files"]] == [a["id"]]
    # b is NOT in the shared folder, so it can't be fetched through this token even though it's a real file id
    assert client.get(f"/public/folders/{token}/files/{b['id']}").status_code == 404


def test_public_folder_endpoints_are_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    try:
        alice, _, rid = _setup(client)
        folder = _mk_folder(client, alice, rid)
        f = _up(client, alice, rid, "a.pdf", PDF)
        client.patch(f"/files/{f['id']}/move", json={"folder_id": folder["id"]}, headers=alice)
        token = client.post(f"/folders/{folder['id']}/share", headers=alice).json()["share_token"]

        for _ in range(30):
            assert client.get(f"/public/folders/{token}").status_code == 200
        r = client.get(f"/public/folders/{token}")
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    finally:
        ratelimit.reset()

"""Public share links for one file at a time (/files/{id}/share, /public/files/{token}).
No login, no membership check on the public endpoint -- that's the point -- so everything
about who can turn it on/off, and that a dead token is really dead, is tested here."""
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


# ---------------------------------------------------------------- turning it on
def test_creator_can_share_their_own_file(client):
    alice, bob, rid = _setup(client)
    f = _up(client, bob, rid, "handout.pdf", PDF)  # Bob is a plain member, but it's his file
    r = client.post(f"/files/{f['id']}/share", headers=bob)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_public"] is True
    assert body["share_token"] and len(body["share_token"]) >= 20


def test_admin_can_share_someone_elses_file(client):
    alice, bob, rid = _setup(client)
    f = _up(client, bob, rid, "handout.pdf", PDF)
    r = client.post(f"/files/{f['id']}/share", headers=alice)  # Alice is admin, not the creator
    assert r.status_code == 200
    assert r.json()["is_public"] is True


def test_plain_member_cannot_share_someone_elses_file(client):
    alice, bob, rid = _setup(client)
    f = _up(client, alice, rid, "handout.pdf", PDF)  # Alice's file
    r = client.post(f"/files/{f['id']}/share", headers=bob)  # Bob: plain member, not the creator
    assert r.status_code == 403


def test_non_member_cannot_share_and_gets_404(client):
    alice, _, rid = _setup(client)
    f = _up(client, alice, rid, "handout.pdf", PDF)
    stranger = signup(client, "stranger@example.com", "Stranger")
    assert client.post(f"/files/{f['id']}/share", headers=stranger).status_code == 404


def test_sharing_twice_keeps_the_same_token(client):
    alice, _, rid = _setup(client)
    f = _up(client, alice, rid, "handout.pdf", PDF)
    first = client.post(f"/files/{f['id']}/share", headers=alice).json()["share_token"]
    second = client.post(f"/files/{f['id']}/share", headers=alice).json()["share_token"]
    assert first == second


# ---------------------------------------------------------------- visibility of the token
def test_creator_and_admin_both_see_the_token_in_the_list(client):
    alice, bob, rid = _setup(client)
    f = _up(client, bob, rid, "handout.pdf", PDF)  # Bob's file
    client.post(f"/files/{f['id']}/share", headers=bob)

    mine = next(x for x in client.get(f"/rooms/{rid}/files", headers=bob).json() if x["id"] == f["id"])
    assert mine["is_public"] is True and mine["share_token"]

    admin_view = next(x for x in client.get(f"/rooms/{rid}/files", headers=alice).json() if x["id"] == f["id"])
    assert admin_view["is_public"] is True and admin_view["share_token"] == mine["share_token"]


def test_plain_member_sees_is_public_but_never_the_token(client):
    alice, _, rid = _setup(client)  # Alice: creator and admin
    carol = signup(client, "carol@example.com", "Carol")  # a third, plain member of the same room
    invite_code = [room for room in client.get("/rooms", headers=alice).json() if room["id"] == rid][0]["invite_code"]
    join_room(client, carol, invite_code)

    f = _up(client, alice, rid, "handout.pdf", PDF)
    client.post(f"/files/{f['id']}/share", headers=alice)

    seen = next(x for x in client.get(f"/rooms/{rid}/files", headers=carol).json() if x["id"] == f["id"])
    assert seen["is_public"] is True
    assert seen["share_token"] is None


# ---------------------------------------------------------------- turning it off
def test_turning_it_off_kills_the_old_link(client):
    alice, _, rid = _setup(client)
    f = _up(client, alice, rid, "handout.pdf", PDF)
    token = client.post(f"/files/{f['id']}/share", headers=alice).json()["share_token"]
    assert client.get(f"/public/files/{token}").status_code == 200

    off = client.delete(f"/files/{f['id']}/share", headers=alice)
    assert off.status_code == 200
    assert off.json()["is_public"] is False
    assert off.json()["share_token"] is None

    assert client.get(f"/public/files/{token}").status_code == 404  # the old link is dead, immediately


def test_plain_member_cannot_turn_off_someone_elses_share(client):
    alice, bob, rid = _setup(client)
    f = _up(client, alice, rid, "handout.pdf", PDF)
    client.post(f"/files/{f['id']}/share", headers=alice)
    assert client.delete(f"/files/{f['id']}/share", headers=bob).status_code == 403


# ---------------------------------------------------------------- the public endpoint itself
def test_public_download_needs_no_login_and_no_membership(client):
    alice, _, rid = _setup(client)
    f = _up(client, alice, rid, "handout.pdf", PDF)
    token = client.post(f"/files/{f['id']}/share", headers=alice).json()["share_token"]

    r = client.get(f"/public/files/{token}")  # no Authorization header at all
    assert r.status_code == 200
    assert r.content == PDF
    assert r.headers["content-type"] == "application/octet-stream"
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_sharing_one_file_does_not_expose_the_rest_of_the_room(client):
    alice, _, rid = _setup(client)
    shared = _up(client, alice, rid, "public.pdf", PDF)
    private = _up(client, alice, rid, "private.pdf", PDF)
    client.post(f"/files/{shared['id']}/share", headers=alice)

    # a random/guessed token never matches a real file
    assert client.get("/public/files/not-a-real-token").status_code == 404
    # the private file was never shared, so it has no public route at all
    assert client.get(f"/files/{private['id']}/download").status_code == 401  # still needs login, as before


def test_public_download_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    try:
        alice, _, rid = _setup(client)
        f = _up(client, alice, rid, "handout.pdf", PDF)
        token = client.post(f"/files/{f['id']}/share", headers=alice).json()["share_token"]
        for _ in range(30):
            assert client.get(f"/public/files/{token}").status_code == 200
        r = client.get(f"/public/files/{token}")
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    finally:
        ratelimit.reset()

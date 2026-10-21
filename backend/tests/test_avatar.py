"""Profile photos: the upload is re-drawn by the server, so nothing hidden in a file can survive."""
import io
import struct
import zlib

import pytest
from PIL import Image, PngImagePlugin

from app import ratelimit
from app.db import SessionLocal
from app.models import UserAvatar
from app.routers import avatar as avatar_module

from .conftest import join_room, make_room, signup


def _png(size=(40, 40), color=(200, 30, 30), mode="RGB", **save):
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, "PNG", **save)
    return out.getvalue()


def _jpeg(size=(40, 40), **save):
    out = io.BytesIO()
    Image.new("RGB", size, (30, 30, 200)).save(out, "JPEG", **save)
    return out.getvalue()


def _put(client, headers, data, content_type="image/png"):
    return client.put("/users/me/avatar", content=data, headers={**headers, "Content-Type": content_type})


def _get(client, headers, user_id):
    return client.get(f"/users/{user_id}/avatar", headers=headers)


def _me(client, headers):
    return client.get("/users/me", headers=headers).json()


def _stored(r):
    img = Image.open(io.BytesIO(r.content))
    img.load()
    return img


# ---------- happy path ----------

def test_upload_and_download_gives_a_clean_256_jpeg(client):
    alice = signup(client)
    uid = _me(client, alice)["id"]
    r = _put(client, alice, _png((300, 120)))
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"].startswith(f"/users/{uid}/avatar?v=")
    got = _get(client, alice, uid)
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/jpeg"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.content[:3] == b"\xff\xd8\xff"  # JPEG magic bytes
    img = _stored(got)
    assert img.format == "JPEG" and img.size == (256, 256)  # non-square input was cropped to a square


def test_jpeg_and_webp_are_accepted(client):
    alice = signup(client)
    assert _put(client, alice, _jpeg(), "image/jpeg").status_code == 200
    out = io.BytesIO()
    Image.new("RGB", (50, 50), (1, 2, 3)).save(out, "WEBP")
    assert _put(client, alice, out.getvalue(), "image/webp").status_code == 200


def test_transparent_png_becomes_white(client):
    alice = signup(client)
    uid = _me(client, alice)["id"]
    assert _put(client, alice, _png((64, 64), (0, 0, 0, 0), mode="RGBA")).status_code == 200
    r, g, b = _stored(_get(client, alice, uid)).getpixel((5, 5))
    assert min(r, g, b) > 240


def test_the_content_type_header_and_file_name_do_not_matter(client):
    alice = signup(client)
    assert _put(client, alice, _png(), "text/plain").status_code == 200  # judged by content only


# ---------- hostile files ----------

def test_not_an_image_is_422(client):
    alice = signup(client)
    for junk in (b"just some text", b"<html><script>alert(1)</script></html>", b"\x00" * 500, b"GIF89a" + b"\x00" * 50):
        assert _put(client, alice, junk, "image/png").status_code == 422
    assert _put(client, alice, b"").status_code == 422


def test_svg_gif_and_bmp_are_refused_even_when_valid(client):
    alice = signup(client)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><rect width="9" height="9"/></svg>'
    assert _put(client, alice, svg, "image/svg+xml").status_code == 422
    for fmt in ("GIF", "BMP"):
        out = io.BytesIO()
        Image.new("RGB", (20, 20), (9, 9, 9)).save(out, fmt)
        assert _put(client, alice, out.getvalue()).status_code == 422, fmt


def test_truncated_image_is_422(client):
    alice = signup(client)
    assert _put(client, alice, _png((200, 200))[:60]).status_code == 422


def test_script_after_the_image_does_not_survive(client):
    alice = signup(client)
    uid = _me(client, alice)["id"]
    evil = b"<script>alert('xss')</script><?php system($_GET['c']); ?>"
    for data in (_png() + evil, _jpeg() + evil):
        assert _put(client, alice, data).status_code == 200
        stored = _get(client, alice, uid).content
        assert b"<script" not in stored and b"<?php" not in stored and b"system(" not in stored


def test_script_inside_image_metadata_does_not_survive(client):
    alice = signup(client)
    uid = _me(client, alice)["id"]
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Comment", "<script>alert(1)</script>")
    assert _put(client, alice, _png(pnginfo=meta)).status_code == 200
    assert b"<script" not in _get(client, alice, uid).content
    exif = Image.Exif()
    exif[0x010E] = "<script>alert(2)</script>"  # ImageDescription
    exif[0x8825] = {1: "N", 2: (14.0, 59.0, 0.0), 3: "E", 4: (120.0, 35.0, 0.0)}  # GPS block
    assert _put(client, alice, _jpeg(exif=exif.tobytes()), "image/jpeg").status_code == 200
    got = _get(client, alice, uid).content
    assert b"<script" not in got and b"Exif" not in got
    assert len(_stored(_get(client, alice, uid)).getexif()) == 0


def test_image_bomb_is_refused(client):
    alice = signup(client)
    png = bytearray(_png((1, 1)))
    ihdr = png.index(b"IHDR") + 4
    png[ihdr:ihdr + 8] = struct.pack(">II", 20000, 20000)  # claims 400 million pixels
    png[ihdr + 13:ihdr + 17] = struct.pack(">I", zlib.crc32(bytes(png[ihdr - 4:ihdr + 13])))
    assert _put(client, alice, bytes(png)).status_code == 422


def test_pixel_limit_is_enforced(client, monkeypatch):
    alice = signup(client)
    monkeypatch.setattr(avatar_module, "MAX_PIXELS", 100)
    assert _put(client, alice, _png((20, 20))).status_code == 422  # 400 pixels is over the (lowered) limit
    assert _put(client, alice, _png((10, 10))).status_code == 200


def test_oversized_upload_is_413(client):
    alice = signup(client)
    r = _put(client, alice, b"0" * (avatar_module.MAX_BYTES + 1))
    assert r.status_code == 413
    assert _get(client, alice, _me(client, alice)["id"]).status_code == 404  # nothing was stored


def test_oversized_chunked_upload_is_413(client):
    alice = signup(client)

    def chunks():
        for _ in range(3):
            yield b"0" * (1024 * 1024)  # no Content-Length is declared, the limit is applied while reading

    r = client.put("/users/me/avatar", content=chunks(), headers={**alice, "Content-Type": "image/png"})
    assert r.status_code == 413


# ---------- who can see it ----------

def test_visibility_rules(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    carol = signup(client, "c@example.com", "Carol")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    a_id, c_id = _me(client, alice)["id"], _me(client, carol)["id"]
    _put(client, alice, _png())
    assert _get(client, alice, a_id).status_code == 200            # me
    assert _get(client, bob, a_id).status_code == 200              # shares a room
    assert _get(client, carol, a_id).status_code == 404            # a stranger: same answer as "no photo"
    assert _get(client, alice, c_id).status_code == 404            # no photo and no shared room
    assert _get(client, alice, 999999).status_code == 404          # unknown user
    assert client.get(f"/users/{a_id}/avatar").status_code == 401  # no token
    assert client.put("/users/me/avatar", content=_png()).status_code == 401
    assert client.delete("/users/me/avatar").status_code == 401


def test_a_member_without_a_photo_gets_404(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    assert _get(client, alice, _me(client, bob)["id"]).status_code == 404


# ---------- the URL shows up where the frontend needs it ----------

def test_avatar_url_in_profile_and_member_list(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    a_id = _me(client, alice)["id"]
    assert _me(client, alice)["avatar_url"] is None
    url = _put(client, alice, _png()).json()["avatar_url"]
    assert _me(client, alice)["avatar_url"] == url
    members = {m["user_id"]: m for m in client.get(f"/rooms/{room['id']}/members", headers=bob).json()}
    assert members[a_id]["avatar_url"] == url
    assert members[_me(client, bob)["id"]]["avatar_url"] is None


def test_replacing_and_deleting(client):
    alice = signup(client)
    uid = _me(client, alice)["id"]
    _put(client, alice, _png(color=(255, 0, 0)))
    first = _get(client, alice, uid).content
    _put(client, alice, _png(color=(0, 0, 255)))
    assert _get(client, alice, uid).content != first
    with SessionLocal() as db:
        assert db.query(UserAvatar).filter(UserAvatar.user_id == uid).count() == 1
    assert client.delete("/users/me/avatar", headers=alice).status_code == 204
    assert client.delete("/users/me/avatar", headers=alice).status_code == 204  # deleting twice is fine
    assert _get(client, alice, uid).status_code == 404
    assert _me(client, alice)["avatar_url"] is None


def test_deleting_the_account_deletes_the_photo(client):
    alice = signup(client)
    uid = _me(client, alice)["id"]
    _put(client, alice, _png())
    assert client.delete("/users/me", headers=alice).status_code == 204
    with SessionLocal() as db:
        assert db.query(UserAvatar).filter(UserAvatar.user_id == uid).count() == 0


# ---------- rate limit ----------

def test_uploads_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    try:
        alice = signup(client)
        bob = signup(client, "b@example.com", "Bob")
        data = _png()
        for _ in range(10):
            assert _put(client, alice, data).status_code == 200
        r = _put(client, alice, data)
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
        assert _put(client, bob, data).status_code == 200  # another user is not affected
    finally:
        ratelimit.reset()
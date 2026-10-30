"""Notes: files shared in a room. Everything an upload could do wrong is tested here."""
import io
import zipfile

import pytest

from app import ratelimit
from app.db import SessionLocal
from app.models import RoomFile
from app.routers import notes as notes_module

from .conftest import join_room, make_room, signup

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def _docx(extra=None, drop=None):
    out = io.BytesIO()
    parts = {"[Content_Types].xml": "<Types/>", "word/document.xml": "<w:document/>", "_rels/.rels": "<Relationships/>"}
    parts.update(extra or {})
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts.items():
            if name != drop:
                z.writestr(name, text)
    return out.getvalue()


def _setup(client):
    alice = signup(client)  # room creator = admin
    bob = signup(client, "b@example.com", "Bob")  # plain member
    room = make_room(client, alice)
    join_room(client, bob, room["invite_code"])
    return alice, bob, room["id"]


def _up(client, headers, rid, name, data):
    return client.post(f"/rooms/{rid}/files", params={"name": name}, content=data,
                       headers={**headers, "Content-Type": "application/octet-stream"})


def _list(client, headers, rid, **params):
    return client.get(f"/rooms/{rid}/files", params=params, headers=headers)


GOOD = [
    ("notes.pdf", PDF, "files"),
    ("essay.docx", _docx(), "docs"),
    ("readme.txt", b"hello\n", "files"),
    ("README.md", b"# Title\n", "files"),
    ("grades.csv", b"a,b\n1,2\n", "files"),
    ("Main.java", b"public class Main { public static void main(String[] a) {} }\n", "files"),
    ("solve.py", b"print('hi')\n", "files"),
    ("sort.cpp", b"#include <iostream>\nint main() { return 0; }\n", "files"),
    ("sort.h", b"#pragma once\n", "files"),
    ("data.json", b'{"a": 1}', "files"),
    ("accents.py", "# café ñ 日本\n".encode("utf-8"), "files"),
    ("bom.txt", b"\xef\xbb\xbfhello", "files"),
]


@pytest.mark.parametrize("name,data,kind", GOOD)
def test_good_files_upload_list_and_download(client, name, data, kind):
    alice, bob, rid = _setup(client)
    r = _up(client, alice, rid, name, data)
    assert r.status_code == 201, r.text
    f = r.json()
    assert (f["name"], f["kind"], f["size"], f["room_id"]) == (name, kind, len(data), rid)
    assert f["created_by_name"] == "Alice" and f["locked"] is False and f["version"] == 1
    assert f["created_at"].endswith("Z")
    assert [x["id"] for x in _list(client, bob, rid).json()] == [f["id"]]  # a room-mate sees it
    d = client.get(f"/files/{f['id']}/download", headers=bob)  # and can download it
    assert d.status_code == 200 and d.content == data


def test_download_is_always_a_plain_attachment(client):
    alice, _, rid = _setup(client)
    f = _up(client, alice, rid, "my notes (final).pdf", PDF).json()
    h = client.get(f"/files/{f['id']}/download", headers=alice).headers
    assert h["content-type"] == "application/octet-stream"
    assert h["content-disposition"].startswith("attachment;")
    assert 'filename="my notes (final).pdf"' in h["content-disposition"]
    assert h["x-content-type-options"] == "nosniff"
    assert "no-store" in h["cache-control"]


def test_unicode_name_gets_an_ascii_fallback_and_a_utf8_name(client):
    alice, _, rid = _setup(client)
    f = _up(client, alice, rid, "résumé café.txt", b"x").json()
    d = client.get(f"/files/{f['id']}/download", headers=alice).headers["content-disposition"]
    assert 'filename="r_sum_ caf_.txt"' in d
    assert "filename*=UTF-8''r%C3%A9sum%C3%A9%20caf%C3%A9.txt" in d


# ---------------------------------------------------------------- who may do what
def test_no_token_is_401_everywhere(client):
    alice, _, rid = _setup(client)
    f = _up(client, alice, rid, "a.txt", b"x").json()
    assert client.get(f"/rooms/{rid}/files").status_code == 401
    assert client.post(f"/rooms/{rid}/files", params={"name": "a.txt"}, content=b"x").status_code == 401
    assert client.get(f"/files/{f['id']}/download").status_code == 401
    assert client.get(f"/files/{f['id']}/text").status_code == 401
    assert client.delete(f"/files/{f['id']}").status_code == 401


def test_outsider_cannot_list_upload_download_preview_or_delete(client):
    alice, _, rid = _setup(client)
    eve = signup(client, "eve@example.com", "Eve")
    f = _up(client, alice, rid, "secret.txt", b"private").json()
    assert _list(client, eve, rid).status_code == 403
    assert _up(client, eve, rid, "x.txt", b"x").status_code == 403
    for r in (client.get(f"/files/{f['id']}/download", headers=eve),
              client.get(f"/files/{f['id']}/text", headers=eve),
              client.delete(f"/files/{f['id']}", headers=eve)):
        assert r.status_code == 404  # same answer as a file that does not exist
    assert client.get("/files/99999/download", headers=eve).status_code == 404
    assert client.get(f"/files/{f['id']}/download", headers=alice).status_code == 200  # still there


def test_files_stay_inside_their_room(client):
    alice, bob, rid = _setup(client)
    other = make_room(client, bob, "Other")["id"]
    f = _up(client, alice, rid, "mine.txt", b"x").json()
    assert _list(client, bob, other).json() == []
    assert _list(client, bob, rid).json()[0]["id"] == f["id"]


def test_delete_rules(client):
    alice = signup(client)
    bob = signup(client, "b@example.com", "Bob")
    carol = signup(client, "c@example.com", "Carol")
    room = make_room(client, alice)
    rid = room["id"]
    join_room(client, bob, room["invite_code"])
    join_room(client, carol, room["invite_code"])
    by_bob = _up(client, bob, rid, "bob.txt", b"x").json()
    assert client.delete(f"/files/{by_bob['id']}", headers=carol).status_code == 403  # another member
    assert client.delete(f"/files/{by_bob['id']}", headers=bob).status_code == 204  # the uploader
    assert client.get(f"/files/{by_bob['id']}/download", headers=alice).status_code == 404
    by_bob2 = _up(client, bob, rid, "bob2.txt", b"x").json()
    assert client.delete(f"/files/{by_bob2['id']}", headers=alice).status_code == 204  # a room admin
    assert _list(client, alice, rid).json() == []


# ---------------------------------------------------------------- what is refused
@pytest.mark.parametrize("name", [
    "virus.exe", "page.html", "image.svg", "bundle.zip", "macro.docm", "old.doc", "run.sh", "run.bat",
    "index.php", "noextension", "photo.png", "sheet.xlsx", ".pdf", "evil.pdf.exe", "a.PDF.js.exe",
])
def test_other_file_types_are_415(client, name):
    alice, _, rid = _setup(client)
    assert _up(client, alice, rid, name, b"x").status_code in (415,)
    assert _list(client, alice, rid).json() == []


def test_extension_is_case_insensitive(client):
    alice, _, rid = _setup(client)
    assert _up(client, alice, rid, "NOTES.PDF", PDF).status_code == 201


@pytest.mark.parametrize("name,data", [
    ("fake.pdf", b"MZ\x90\x00 this is a program"),
    ("fake.pdf", b"just text"),
    ("fake.docx", b"just text, not a zip"),
    ("fake.docx", b"PK\x03\x04 broken zip"),
    ("nodoc.docx", _docx(drop="word/document.xml")),
    ("noct.docx", _docx(drop="[Content_Types].xml")),
    ("macro.docx", _docx(extra={"word/vbaProject.bin": "x"})),
    ("ole.docx", _docx(extra={"word/embeddings/oleObject1.bin": "x"})),
    ("prog.docx", _docx(extra={"word/media/run.exe": "x"})),
    ("nul.py", b"print('a')\x00\x00"),
    ("latin1.java", b"caf\xe9 \xff\xfe"),
    ("binary.txt", bytes(range(256))),
])
def test_content_must_match_the_name(client, name, data):
    alice, _, rid = _setup(client)
    assert _up(client, alice, rid, name, data).status_code == 422
    assert _list(client, alice, rid).json() == []


@pytest.mark.parametrize("payload", [
    b"/JavaScript (app.alert(1))", b"/S /JavaScript", b"/JS (x)", b"/Launch /Win", b"/Type /EmbeddedFile",
    b"/RichMedia", b"/J#61vaScript", b"/#4AS (x)",
])
def test_pdf_with_scripts_or_embedded_files_is_refused(client, payload):
    alice, _, rid = _setup(client)
    r = _up(client, alice, rid, "bad.pdf", PDF + b"\n" + payload + b"\n")
    assert r.status_code == 422 and "can't be shared" in r.json()["detail"]


def test_ordinary_pdf_features_are_not_mistaken_for_scripts(client):
    alice, _, rid = _setup(client)
    harmless = PDF + b"/OpenAction [3 0 R /Fit] /BaseFont /AAAAAA+Calibri /JSON-like /JSX /Launcher /Javascripty\n"
    assert _up(client, alice, rid, "latex.pdf", harmless).status_code == 201


def test_zip_with_too_many_parts_is_refused(client):
    alice, _, rid = _setup(client)
    many = _docx(extra={f"word/media/{i}.xml": "" for i in range(2001)})
    assert _up(client, alice, rid, "many.docx", many).status_code == 422


def test_empty_file_is_422(client):
    alice, _, rid = _setup(client)
    assert _up(client, alice, rid, "empty.txt", b"").status_code == 422


def test_missing_or_huge_name_is_handled(client):
    alice, _, rid = _setup(client)
    assert client.post(f"/rooms/{rid}/files", content=b"x", headers=alice).status_code == 422  # no ?name=
    assert _up(client, alice, rid, "x" * 301 + ".txt", b"x").status_code == 422


# ---------------------------------------------------------------- names
@pytest.mark.parametrize("sent,stored", [
    ("../../etc/passwd.txt", "passwd.txt"),
    ("C:\\Users\\me\\homework.py", "homework.py"),
    ("a/b/c.md", "c.md"),
    ("<script>alert(1)</script>.txt", "script.txt"),
    ("tab\there\nnewline.txt", "tabherenewline.txt"),
    ("evil\u202egnp.txt", "evilgnp.txt"),
    ("  spaced   out  .txt", "spaced out .txt"),
    ("trailing dots...txt", "trailing dots...txt"),
])
def test_names_are_cleaned(client, sent, stored):
    alice, _, rid = _setup(client)
    r = _up(client, alice, rid, sent, b"x")
    assert r.status_code == 201, r.text
    assert r.json()["name"] == stored


def test_long_names_are_shortened_but_keep_their_extension(client):
    alice, _, rid = _setup(client)
    r = _up(client, alice, rid, "n" * 250 + ".py", b"x")
    assert r.status_code == 201
    assert len(r.json()["name"]) == 100 and r.json()["name"].endswith(".py")


# ---------------------------------------------------------------- size and quota
def test_file_over_5mb_is_413_and_exactly_5mb_is_fine(client):
    alice, _, rid = _setup(client)
    assert _up(client, alice, rid, "big.txt", b"a" * (10 * 1024 * 1024 + 1)).status_code == 413
    assert _up(client, alice, rid, "edge.txt", b"a" * (10 * 1024 * 1024)).status_code == 201


def test_room_file_space_is_limited(client, monkeypatch):
    monkeypatch.setattr(notes_module, "MAX_ROOM_BYTES", 100)
    alice, bob, rid = _setup(client)
    assert _up(client, alice, rid, "one.txt", b"a" * 60).status_code == 201
    r = _up(client, bob, rid, "two.txt", b"a" * 60)
    assert r.status_code == 413 and "full" in r.json()["detail"]
    assert _up(client, bob, rid, "small.txt", b"a" * 40).status_code == 201  # exactly fills it
    first = _list(client, alice, rid, sort="name", order="asc").json()[0]
    client.delete(f"/files/{first['id']}", headers=alice)  # space comes back after a delete
    assert _up(client, bob, rid, "two.txt", b"a" * 60).status_code == 201


def test_uploads_are_limited_to_20_per_hour_per_user(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    try:
        alice, bob, rid = _setup(client)
        for i in range(20):
            assert _up(client, alice, rid, f"f{i}.txt", b"x").status_code == 201
        r = _up(client, alice, rid, "one-too-many.txt", b"x")
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
        assert _up(client, bob, rid, "bob.txt", b"x").status_code == 201  # Bob has his own count
    finally:
        ratelimit.reset()


# ---------------------------------------------------------------- list, sort, filters
def test_list_filters_and_sorting(client):
    alice, _, rid = _setup(client)
    _up(client, alice, rid, "b.txt", b"22")
    _up(client, alice, rid, "A.py", b"1")
    _up(client, alice, rid, "c.docx", _docx())
    names = lambda **p: [f["name"] for f in _list(client, alice, rid, **p).json()]
    assert names() == ["c.docx", "A.py", "b.txt"]  # newest first by default
    assert names(sort="name", order="asc") == ["A.py", "b.txt", "c.docx"]  # not case-sensitive
    assert names(sort="name", order="desc") == ["c.docx", "b.txt", "A.py"]
    assert names(sort="size", order="asc")[0] == "A.py"
    assert names(sort="created", order="asc") == ["b.txt", "A.py", "c.docx"]
    assert names(kind="docs") == ["c.docx"]
    assert names(kind="files") == ["A.py", "b.txt"]
    assert names(kind="sheets") == []


@pytest.mark.parametrize("params", [{"sort": "colour"}, {"order": "sideways"}, {"kind": "videos"}])
def test_bad_list_options_are_422(client, params):
    alice, _, rid = _setup(client)
    assert _list(client, alice, rid, **params).status_code == 422


# ---------------------------------------------------------------- text preview
def test_text_preview_for_code_and_text(client):
    alice, bob, rid = _setup(client)
    f = _up(client, alice, rid, "hello.py", b"\xef\xbb\xbfprint('<b>hi</b>')\n").json()
    r = client.get(f"/files/{f['id']}/text", headers=bob)
    assert r.status_code == 200
    assert r.json() == {"name": "hello.py", "text": "print('<b>hi</b>')\n", "truncated": False}


def test_text_preview_is_cut_off_when_long(client):
    alice, _, rid = _setup(client)
    f = _up(client, alice, rid, "long.txt", b"a" * 250_000).json()
    r = client.get(f"/files/{f['id']}/text", headers=alice).json()
    assert r["truncated"] is True and len(r["text"]) == 200_000


def test_no_text_preview_for_pdf_or_docx(client):
    alice, _, rid = _setup(client)
    for name, data in (("a.pdf", PDF), ("b.docx", _docx())):
        f = _up(client, alice, rid, name, data).json()
        assert client.get(f"/files/{f['id']}/text", headers=alice).status_code == 415


# ---------------------------------------------------------------- housekeeping
def test_files_vanish_with_the_room(client):
    alice = signup(client)
    rid = make_room(client, alice)["id"]
    _up(client, alice, rid, "a.txt", b"x")
    assert client.post(f"/rooms/{rid}/leave", headers=alice).status_code in (200, 204)  # last person out
    with SessionLocal() as db:
        assert db.query(RoomFile).count() == 0


def test_uploader_who_deletes_their_account_shows_as_deleted_user(client):
    alice, bob, rid = _setup(client)
    _up(client, bob, rid, "bobs.txt", b"x")
    assert client.delete("/users/me", headers=bob).status_code == 204
    assert _list(client, alice, rid).json()[0]["created_by_name"] == "Deleted user"

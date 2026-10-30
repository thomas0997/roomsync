"""Notes files kept in Cloudflare R2. A fake in-memory bucket stands in for R2 (no network in tests)."""
import pytest

from app import storage
from app.db import SessionLocal
from app.models import RoomFile
from app.routers import notes as notes_module

from .conftest import join_room, make_room, signup
from .test_files import _list, _setup, _up


@pytest.fixture()
def r2(monkeypatch):
    bucket = {}

    def put(key, data):
        bucket[key] = bytes(data)

    def get(key, limit=None):
        if key not in bucket:
            raise storage.StorageError("missing")
        return bucket[key] if limit is None else bucket[key][:limit]

    def delete_many(keys):
        for key in keys:
            bucket.pop(key, None)

    monkeypatch.setattr(storage, "enabled", lambda: True)
    monkeypatch.setattr(storage, "put", put)
    monkeypatch.setattr(storage, "get", get)
    monkeypatch.setattr(storage, "delete_many", delete_many)
    return bucket


def test_enabled_needs_all_four_values(monkeypatch):
    for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.setenv(name, "x")
    assert storage.enabled() is True
    monkeypatch.delenv("R2_BUCKET")
    assert storage.enabled() is False


def test_upload_goes_to_r2_not_the_database(client, r2):
    alice, bob, rid = _setup(client)
    r = _up(client, alice, rid, "solve.py", b"print('hi')\n")
    assert r.status_code == 201
    assert "storage_key" not in r.json()                     # the object key is never sent to the browser
    assert len(r2) == 1 and next(iter(r2)).startswith(f"rooms/{rid}/") and "solve" not in next(iter(r2))
    with SessionLocal() as s:
        row = s.query(RoomFile).one()
        assert row.storage_key is not None and row.data is None
    d = client.get(f"/files/{r.json()['id']}/download", headers=bob)
    assert d.status_code == 200 and d.content == b"print('hi')\n"
    assert d.headers["content-type"] == "application/octet-stream" and "attachment" in d.headers["content-disposition"]


def test_preview_reads_only_the_start_of_an_r2_file(client, r2):
    alice, _, rid = _setup(client)
    fid = _up(client, alice, rid, "big.txt", b"a" * 300_000).json()["id"]
    t = client.get(f"/files/{fid}/text", headers=alice).json()
    assert len(t["text"]) == notes_module.PREVIEW_BYTES and t["truncated"] is True
    small = _up(client, alice, rid, "small.txt", b"hello").json()["id"]
    t = client.get(f"/files/{small}/text", headers=alice).json()
    assert t["text"] == "hello" and t["truncated"] is False


def test_deleting_a_file_removes_it_from_r2(client, r2):
    alice, bob, rid = _setup(client)
    fid = _up(client, bob, rid, "mine.txt", b"x").json()["id"]
    assert len(r2) == 1
    assert client.delete(f"/files/{fid}", headers=alice).status_code == 204   # room admin may delete
    assert r2 == {}


def test_a_refused_delete_keeps_the_object(client, r2):
    alice, bob, rid = _setup(client)
    fid = _up(client, alice, rid, "hers.txt", b"x").json()["id"]
    assert client.delete(f"/files/{fid}", headers=bob).status_code == 403
    assert len(r2) == 1


def test_deleting_the_room_removes_its_files_from_r2(client, r2):
    alice, bob, rid = _setup(client)
    _up(client, alice, rid, "a.txt", b"1")
    _up(client, bob, rid, "b.txt", b"2")
    assert len(r2) == 2
    assert client.post(f"/rooms/{rid}/leave", headers=bob).status_code == 204
    assert len(r2) == 2                                        # the room still exists
    assert client.post(f"/rooms/{rid}/leave", headers=alice).status_code == 204   # last one out: room is deleted
    assert r2 == {}


def test_a_rolled_back_delete_never_touches_r2(client, r2):
    alice, _, rid = _setup(client)
    _up(client, alice, rid, "keep.txt", b"x")
    with SessionLocal() as s:
        row = s.query(RoomFile).one()
        s.delete(row)
        s.flush()
        s.rollback()
        assert len(r2) == 1
        s.delete(s.query(RoomFile).one())
        s.commit()
    assert r2 == {}


def test_r2_down_on_upload_stores_nothing(client, r2, monkeypatch):
    alice, _, rid = _setup(client)

    def broken(key, data):
        raise storage.StorageError("down")

    monkeypatch.setattr(storage, "put", broken)
    r = _up(client, alice, rid, "a.txt", b"x")
    assert r.status_code == 503 and "try again" in r.json()["detail"].lower()
    assert _list(client, alice, rid).json() == [] and r2 == {}


def test_r2_down_on_download_gives_503(client, r2, monkeypatch):
    alice, _, rid = _setup(client)
    fid = _up(client, alice, rid, "a.txt", b"x").json()["id"]
    r2.clear()                                                 # the object has vanished
    assert client.get(f"/files/{fid}/download", headers=alice).status_code == 503
    assert client.get(f"/files/{fid}/text", headers=alice).status_code == 503


def test_files_from_before_r2_still_work_and_count_toward_the_room(client, r2, monkeypatch):
    alice, bob, rid = _setup(client)
    monkeypatch.setattr(storage, "enabled", lambda: False)     # uploaded back when files lived in the database
    old = _up(client, alice, rid, "old.txt", b"a" * 60).json()["id"]
    monkeypatch.setattr(storage, "enabled", lambda: True)
    assert r2 == {}
    assert client.get(f"/files/{old}/download", headers=bob).content == b"a" * 60
    monkeypatch.setattr(notes_module, "MAX_ROOM_BYTES", 100)
    assert _up(client, bob, rid, "new.txt", b"a" * 60).status_code == 413     # 60 (database) + 60 (R2) > 100
    assert _up(client, bob, rid, "new.txt", b"a" * 40).status_code == 201
    client.delete(f"/files/{old}", headers=alice)
    assert len(r2) == 1                                        # deleting the old one didn't touch R2


def test_whole_app_cap_stops_uploads_across_rooms(client, r2, monkeypatch):
    monkeypatch.setattr(notes_module, "MAX_TOTAL_BYTES", 100)
    alice, _, rid = _setup(client)
    other = make_room(client, alice, "Other")["id"]
    assert _up(client, alice, rid, "one.txt", b"a" * 60).status_code == 201
    r = _up(client, alice, other, "two.txt", b"a" * 60)
    assert r.status_code == 507 and "full" in r.json()["detail"]
    assert _up(client, alice, other, "small.txt", b"a" * 40).status_code == 201

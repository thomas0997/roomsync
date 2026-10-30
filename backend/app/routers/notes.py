"""Notes: files shared in a room. Thomas's file. Follows docs/api-contract.md ("Files").

A classmate could upload anything, so we trust nothing:
 - Only an allowlist of file types (app/filecheck.py), and the CONTENT must match the name: a .pdf must be a
   real PDF without scripts, a .docx a real Word file without macros, code and text must be valid UTF-8.
 - The server never opens, unpacks or runs an uploaded file. It only stores the bytes.
 - Files come back ONLY as a download ("attachment", generic type, nosniff), never as a web page.
 - Only room members can list or fetch files. A file in someone else's room looks exactly like a missing one (404).
 - The bytes live in Cloudflare R2 (private bucket; see app/storage.py), or in the database table room_files when R2 is
   not configured. Limits: 10 MB per file, 500 MB per room, 8 GB for the whole app, 20 uploads an hour per user."""
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import storage
from ..auth import get_current_user, require_member
from ..db import get_db
from ..filecheck import ALLOWED, ALLOWED_LIST, TEXT_EXTENSIONS, check_content, clean_name, extension_of
from ..models import Membership, RoomFile, User
from ..ratelimit import limit_by_user
from ..schemas_files import FileOut, FileTextOut

router = APIRouter(tags=["notes"])

MAX_FILE_BYTES = 10 * 1024 * 1024     # biggest single file
MAX_ROOM_BYTES = 500 * 1024 * 1024    # all files in one room together
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024  # every room together (stays under R2's 10 GB free tier)
PREVIEW_BYTES = 200_000               # how much of a text/code file the in-page viewer shows


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "File not found")


def _uploader_name(user: User | None) -> str:
    return "Deleted user" if user is None or user.deleted_at is not None else user.name


def _out(f: RoomFile, uploader: User | None) -> FileOut:
    name = _uploader_name(uploader)
    return FileOut(
        id=f.id, room_id=f.room_id, name=f.name, kind=f.kind, mime=f.mime, size=f.size, locked=False,
        created_by=f.created_by, created_by_name=name, created_at=f.created_at,
        updated_at=f.created_at, updated_by_name=name, version=1,
    )


def _file_for_member(db: Session, user: User, file_id: int) -> tuple[RoomFile, Membership]:
    """The file, if it exists AND I am in its room. Missing and not-yours give the same 404."""
    f = db.get(RoomFile, file_id)
    if f is None:
        raise _not_found()
    m = db.query(Membership).filter(Membership.user_id == user.id, Membership.room_id == f.room_id).first()
    if m is None:
        raise _not_found()
    return f, m


async def _read_limited_body(request: Request) -> bytes:
    """Read the upload, but stop as soon as it is over the limit (never load a huge file)."""
    too_big = HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "That file is too big (10 MB maximum).")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_FILE_BYTES:
        raise too_big
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            raise too_big
        chunks.append(chunk)
    return b"".join(chunks)


def _precheck(db: Session, user: User, room_id: int, raw_name: str) -> tuple[str, str]:
    """Before reading the upload: am I a member, and is this a name and type we accept?"""
    require_member(db, user, room_id)
    name = clean_name(raw_name)
    ext = extension_of(name)
    if not name or ext not in ALLOWED:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"That file type is not allowed. Allowed: {ALLOWED_LIST}.")
    return name, ext


def _bytes_of(f: RoomFile, limit: int | None = None) -> bytes:
    """The file's bytes (or just the first `limit`), from R2 or from the database."""
    if f.storage_key is None:
        return f.data if limit is None else f.data[:limit]
    try:
        return storage.get(f.storage_key, limit)
    except storage.StorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Couldn't fetch that file right now. Try again in a minute.")


def _store(db: Session, user: User, room_id: int, name: str, ext: str, raw: bytes) -> FileOut:
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That file is empty.")
    try:
        check_content(ext, raw)
    except ValueError as problem:  # the message is written for the user; we never log the file
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(problem))
    used = db.query(func.coalesce(func.sum(RoomFile.size), 0)).filter(RoomFile.room_id == room_id).scalar()
    if used + len(raw) > MAX_ROOM_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"This room's file space is full ({MAX_ROOM_BYTES // (1024 * 1024)} MB). Delete a file first.",
        )
    everything = db.query(func.coalesce(func.sum(RoomFile.size), 0)).scalar()
    if everything + len(raw) > MAX_TOTAL_BYTES:
        raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "RoomSync's file storage is full right now. Please tell the team.")
    kind, mime = ALLOWED[ext]
    row = RoomFile(room_id=room_id, created_by=user.id, name=name, kind=kind, mime=mime, size=len(raw))
    key = None
    if storage.enabled():
        key = storage.new_key(room_id)
        try:
            storage.put(key, raw)
        except storage.StorageError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "File storage is not available right now. Try again in a minute.")
        row.storage_key = key
    else:
        row.data = raw
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        if key:
            storage.delete_many([key])  # don't leave an orphan in R2
        raise
    db.refresh(row)
    return _out(row, user)


@router.get("/rooms/{room_id}/files", response_model=list[FileOut])
def list_files(
    room_id: int,
    kind: Literal["docs", "sheets", "files"] | None = None,
    sort: Literal["modified", "created", "name", "size"] = "modified",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_member(db, user, room_id)
    query = db.query(RoomFile, User).join(User, User.id == RoomFile.created_by).filter(RoomFile.room_id == room_id)
    if kind:
        query = query.filter(RoomFile.kind == kind)
    column = {"modified": RoomFile.created_at, "created": RoomFile.created_at,
              "name": func.lower(RoomFile.name), "size": RoomFile.size}[sort]
    direction = (lambda c: c.asc()) if order == "asc" else (lambda c: c.desc())
    rows = query.order_by(direction(column), direction(RoomFile.id)).all()
    return [_out(f, uploader) for f, uploader in rows]


@router.post(
    "/rooms/{room_id}/files",
    response_model=FileOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_by_user("file_upload", 20, 3600))],
)
async def upload_file(
    room_id: int,
    request: Request,
    name: str = Query(min_length=1, max_length=300),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The body is the raw file (not a form); its name goes in ?name=. Checks run cheapest first."""
    clean, ext = await run_in_threadpool(_precheck, db, user, room_id, name)
    raw = await _read_limited_body(request)
    return await run_in_threadpool(_store, db, user, room_id, clean, ext, raw)


def _disposition(name: str) -> str:
    fallback = "".join(ch if ch.isascii() and ch not in '"\\' else "_" for ch in name)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8\'\'{quote(name, safe='')}"


@router.get("/files/{file_id}/download")
def download_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f, _ = _file_for_member(db, user, file_id)
    # Always a generic download, never shown as a page: the browser can't run or render it from our site.
    return Response(
        content=_bytes_of(f),
        media_type="application/octet-stream",
        headers={"Content-Disposition": _disposition(f.name), "X-Content-Type-Options": "nosniff"},
    )


@router.get("/files/{file_id}/text", response_model=FileTextOut)
def file_text(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The first part of a text or code file, for the in-page viewer (the page shows it as plain text)."""
    f, _ = _file_for_member(db, user, file_id)
    if extension_of(f.name) not in TEXT_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "No text preview for this kind of file. Download it instead.")
    text = _bytes_of(f, PREVIEW_BYTES).decode("utf-8-sig", errors="replace")
    return FileTextOut(name=f.name, text=text, truncated=f.size > PREVIEW_BYTES)


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f, membership = _file_for_member(db, user, file_id)
    if f.created_by != user.id and membership.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who shared this file or a room admin can delete it")
    db.delete(f)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

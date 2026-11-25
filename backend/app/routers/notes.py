"""Notes: files shared in a room. Thomas's file. Follows docs/api-contract.md ("Files").

A classmate could upload anything, so we trust nothing:
 - Only an allowlist of file types (app/filecheck.py), and the CONTENT must match the name: a .pdf must be a
   real PDF without scripts, a .docx a real Word file without macros, code and text must be valid UTF-8.
 - The server never opens, unpacks or runs an uploaded file. It only stores the bytes.
 - Files come back ONLY as a download ("attachment", generic type, nosniff), never as a web page.
 - Only room members can list or fetch files. A file in someone else's room looks exactly like a missing one (404).
 - The bytes live in Cloudflare R2 (private bucket; see app/storage.py), or in the database table room_files when R2 is
   not configured. Limits: 10 MB per file, 500 MB per room, 8 GB for the whole app, 20 uploads an hour per user.

Public share links (/files/{id}/share, /public/files/{token}): the creator or a room admin can make ONE file,
and only that file, downloadable with no login and no room membership at all -- for sharing outside RoomSync
(e.g. with a reviewer who has no account). It reuses the same random-token + rate-limit pattern as room invite
codes: a 192-bit `secrets.token_urlsafe` value, so it cannot be guessed, and turning it off (DELETE) makes the
old link 404 immediately. The public endpoint serves the exact same locked-down response as the normal
download (attachment, generic type, nosniff) -- it is never rendered as a page, same as every other file.

Folders (/rooms/{room_id}/folders, /folders/{id}, /files/{id}/move): a flat (no nesting) way to group files
within a room. Any member can create one and move files in and out; only the folder's creator or a room admin
can rename, delete, or (un)share it -- same rule as files. Deleting a folder never deletes its files: they fall
back to the room's root (folder_id -> NULL).

Public folder share links (/folders/{id}/share, /public/folders/{token}, /public/folders/{token}/files/{file_id}):
same no-login model as a single public file, but for every file CURRENTLY in that folder (files added later are
included automatically; nothing outside the folder is ever reachable this way). GET /public/folders/{token}
returns a small listing (name/size/mime per file, no tokens, nothing else about the room); each file is then
downloaded one at a time via GET /public/folders/{token}/files/{file_id}, which re-checks that the file still
sits in that exact folder before serving it."""
import secrets
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import storage
from ..auth import get_current_user, require_member
from ..db import get_db
from ..filecheck import ALLOWED, ALLOWED_LIST, TEXT_EXTENSIONS, check_content, clean_name, extension_of
from ..models import Membership, RoomFile, RoomFolder, Task, TaskFile, User
from ..ratelimit import limit_by_ip, limit_by_user
from ..schemas_files import FileMove, FileOut, FileTextOut, FolderCreate, FolderOut, FolderRename, UsedIn

router = APIRouter(tags=["notes"])

MAX_FILE_BYTES = 10 * 1024 * 1024     # biggest single file
MAX_ROOM_BYTES = 500 * 1024 * 1024    # all files in one room together
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024  # every room together (stays under R2's 10 GB free tier)
PREVIEW_BYTES = 200_000               # how much of a text/code file the in-page viewer shows


def _not_found(what: str = "File") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def _uploader_name(user: User | None) -> str:
    return "Deleted user" if user is None or user.deleted_at is not None else user.name


def _out(f: RoomFile, uploader: User | None, *, can_manage: bool = False) -> FileOut:
    name = _uploader_name(uploader)
    return FileOut(
        id=f.id, room_id=f.room_id, name=f.name, kind=f.kind, mime=f.mime, size=f.size, locked=False,
        created_by=f.created_by, created_by_name=name, created_at=f.created_at,
        updated_at=f.created_at, updated_by_name=name, version=1,
        is_public=f.share_token is not None,
        share_token=f.share_token if can_manage else None,  # only the creator or a room admin sees the token
        folder_id=f.folder_id,
    )


def _can_manage(f: RoomFile, user: User, membership: Membership) -> bool:
    """Same rule as deleting a file: the person who shared it, or a room admin."""
    return f.created_by == user.id or membership.role == "admin"


def _new_share_token(db: Session) -> str:
    while True:
        token = secrets.token_urlsafe(24)
        if not db.query(RoomFile).filter(RoomFile.share_token == token).first():
            return token


def _folder_out(folder: RoomFolder, *, can_manage: bool = False, file_count: int = 0) -> FolderOut:
    return FolderOut(
        id=folder.id, room_id=folder.room_id, name=folder.name, created_by=folder.created_by,
        created_at=folder.created_at, file_count=file_count,
        is_public=folder.share_token is not None,
        share_token=folder.share_token if can_manage else None,
    )


def _can_manage_folder(folder: RoomFolder, user: User, membership: Membership) -> bool:
    """Same rule as files: the person who made the folder, or a room admin."""
    return folder.created_by == user.id or membership.role == "admin"


def _new_folder_share_token(db: Session) -> str:
    while True:
        token = secrets.token_urlsafe(24)
        if not db.query(RoomFolder).filter(RoomFolder.share_token == token).first():
            return token


def _folder_for_member(db: Session, user: User, folder_id: int) -> tuple[RoomFolder, Membership]:
    """The folder, if it exists AND I am in its room. Missing and not-yours give the same 404."""
    folder = db.get(RoomFolder, folder_id)
    if folder is None:
        raise _not_found("Folder")
    m = db.query(Membership).filter(Membership.user_id == user.id, Membership.room_id == folder.room_id).first()
    if m is None:
        raise _not_found("Folder")
    return folder, m


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


def _used_in(db: Session, file_ids: list[int]) -> dict[int, list[UsedIn]]:
    """Which APPROVED tasks link each file (pending and rejected tasks are never shown), in one query."""
    found: dict[int, list[UsedIn]] = {}
    if not file_ids:
        return found
    rows = (
        db.query(TaskFile.file_id, Task.id, Task.title)
        .join(Task, Task.id == TaskFile.task_id)
        .filter(TaskFile.file_id.in_(file_ids), Task.status == "approved")
        .order_by(Task.due_at, Task.id)
        .all()
    )
    for file_id, task_id, title in rows:
        found.setdefault(file_id, []).append(UsedIn(task_id=task_id, title=title))
    return found


@router.get("/rooms/{room_id}/files", response_model=list[FileOut])
def list_files(
    room_id: int,
    kind: Literal["docs", "sheets", "files"] | None = None,
    sort: Literal["modified", "created", "name", "size"] = "modified",
    order: Literal["asc", "desc"] = "desc",
    folder_id: int | None = None,  # only files in this folder
    unfiled: bool = False,  # only files with no folder (the room's root); ignored if folder_id is set
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = require_member(db, user, room_id)
    query = db.query(RoomFile, User).join(User, User.id == RoomFile.created_by).filter(RoomFile.room_id == room_id)
    if kind:
        query = query.filter(RoomFile.kind == kind)
    if folder_id is not None:
        query = query.filter(RoomFile.folder_id == folder_id)
    elif unfiled:
        query = query.filter(RoomFile.folder_id.is_(None))
    column = {"modified": RoomFile.created_at, "created": RoomFile.created_at,
              "name": func.lower(RoomFile.name), "size": RoomFile.size}[sort]
    direction = (lambda c: c.asc()) if order == "asc" else (lambda c: c.desc())
    rows = query.order_by(direction(column), direction(RoomFile.id)).all()
    used = _used_in(db, [f.id for f, _ in rows])
    out = []
    for f, uploader in rows:
        item = _out(f, uploader, can_manage=_can_manage(f, user, membership))
        tasks = used.get(f.id, [])
        item.used_in, item.used_in_count = tasks[:5], len(tasks)
        out.append(item)
    return out


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
    if not _can_manage(f, user, membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who shared this file or a room admin can delete it")
    db.delete(f)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/files/{file_id}/share", response_model=FileOut)
def enable_public_share(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Make this one file downloadable with no login at all, via GET /public/files/{token}. The rest of the
    room, and every other file, stays exactly as private as before."""
    f, membership = _file_for_member(db, user, file_id)
    if not _can_manage(f, user, membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who shared this file or a room admin can make it public")
    if f.share_token is None:
        f.share_token = _new_share_token(db)
        db.commit()
        db.refresh(f)
    return _out(f, db.get(User, f.created_by), can_manage=True)


@router.delete("/files/{file_id}/share", response_model=FileOut)
def disable_public_share(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Turn a public link back off. The old link 404s immediately; a new Share makes a different one."""
    f, membership = _file_for_member(db, user, file_id)
    if not _can_manage(f, user, membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who shared this file or a room admin can turn this off")
    f.share_token = None
    db.commit()
    db.refresh(f)
    return _out(f, db.get(User, f.created_by), can_manage=True)


@router.get("/public/files/{token}", dependencies=[Depends(limit_by_ip("public_file", 30, 3600))])
def public_download(token: str, db: Session = Depends(get_db)):
    """No login, no membership check -- that's the point. Only reachable with the random token from Share,
    and only while that file's public link is still on. A wrong or turned-off token looks exactly like a
    file that was never shared (404), so this can't be used to probe whether a token almost matches."""
    f = db.query(RoomFile).filter(RoomFile.share_token == token).first()
    if f is None:
        raise _not_found()
    return Response(
        content=_bytes_of(f),
        media_type="application/octet-stream",
        headers={"Content-Disposition": _disposition(f.name), "X-Content-Type-Options": "nosniff"},
    )


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------

def _folder_file_count(db: Session, folder_id: int) -> int:
    return db.query(func.count(RoomFile.id)).filter(RoomFile.folder_id == folder_id).scalar() or 0


def _clean_folder_name(raw: str) -> str:
    name = raw.strip()
    if not name or len(name) > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Folder name must be 1-100 characters.")
    return name


@router.get("/rooms/{room_id}/folders", response_model=list[FolderOut])
def list_folders(room_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    membership = require_member(db, user, room_id)
    rows = db.query(RoomFolder).filter(RoomFolder.room_id == room_id).order_by(func.lower(RoomFolder.name)).all()
    counts = dict(
        db.query(RoomFile.folder_id, func.count(RoomFile.id))
        .filter(RoomFile.room_id == room_id, RoomFile.folder_id.isnot(None))
        .group_by(RoomFile.folder_id)
        .all()
    )
    return [
        _folder_out(f, can_manage=_can_manage_folder(f, user, membership), file_count=counts.get(f.id, 0))
        for f in rows
    ]


@router.post("/rooms/{room_id}/folders", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(room_id: int, body: FolderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_member(db, user, room_id)  # any member can make a folder
    row = RoomFolder(room_id=room_id, created_by=user.id, name=_clean_folder_name(body.name))
    db.add(row)
    db.commit()
    db.refresh(row)
    return _folder_out(row, can_manage=True)


@router.patch("/folders/{folder_id}", response_model=FolderOut)
def rename_folder(folder_id: int, body: FolderRename, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    folder, membership = _folder_for_member(db, user, folder_id)
    if not _can_manage_folder(folder, user, membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who made this folder or a room admin can rename it")
    folder.name = _clean_folder_name(body.name)
    db.commit()
    db.refresh(folder)
    return _folder_out(folder, can_manage=True, file_count=_folder_file_count(db, folder.id))


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The folder goes away; its files don't. They fall back to the room's root (folder_id -> NULL)."""
    folder, membership = _folder_for_member(db, user, folder_id)
    if not _can_manage_folder(folder, user, membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who made this folder or a room admin can delete it")
    db.query(RoomFile).filter(RoomFile.folder_id == folder.id).update({"folder_id": None})
    db.delete(folder)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/files/{file_id}/move", response_model=FileOut)
def move_file(file_id: int, body: FileMove, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f, membership = _file_for_member(db, user, file_id)
    if not _can_manage(f, user, membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who shared this file or a room admin can move it")
    if body.folder_id is not None:
        folder = db.get(RoomFolder, body.folder_id)
        if folder is None or folder.room_id != f.room_id:
            raise _not_found("Folder")
    f.folder_id = body.folder_id
    db.commit()
    db.refresh(f)
    return _out(f, db.get(User, f.created_by), can_manage=True)


@router.post("/folders/{folder_id}/share", response_model=FolderOut)
def enable_folder_share(folder_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Make every file CURRENTLY in this folder (and any added later) browsable and downloadable with no
    login, via GET /public/folders/{token}. Nothing outside the folder is ever reachable this way."""
    folder, membership = _folder_for_member(db, user, folder_id)
    if not _can_manage_folder(folder, user, membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who made this folder or a room admin can make it public")
    if folder.share_token is None:
        folder.share_token = _new_folder_share_token(db)
        db.commit()
        db.refresh(folder)
    return _folder_out(folder, can_manage=True, file_count=_folder_file_count(db, folder.id))


@router.delete("/folders/{folder_id}/share", response_model=FolderOut)
def disable_folder_share(folder_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Turn a folder's public link back off. The old link 404s immediately, same as a file's."""
    folder, membership = _folder_for_member(db, user, folder_id)
    if not _can_manage_folder(folder, user, membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who made this folder or a room admin can turn this off")
    folder.share_token = None
    db.commit()
    db.refresh(folder)
    return _folder_out(folder, can_manage=True, file_count=_folder_file_count(db, folder.id))


class PublicFolderFile(BaseModel):
    id: int
    name: str
    kind: str  # "docs" | "sheets" | "files"
    mime: str
    size: int


class PublicFolderOut(BaseModel):
    name: str
    files: list[PublicFolderFile]


@router.get(
    "/public/folders/{token}",
    response_model=PublicFolderOut,
    dependencies=[Depends(limit_by_ip("public_folder", 30, 3600))],
)
def public_folder_listing(token: str, db: Session = Depends(get_db)):
    """No login, no membership check. Lists only name/size/kind per file -- no tokens, no room info, nothing
    about who uploaded what. A wrong or turned-off token looks exactly like a folder that was never shared."""
    folder = db.query(RoomFolder).filter(RoomFolder.share_token == token).first()
    if folder is None:
        raise _not_found("Folder")
    files = db.query(RoomFile).filter(RoomFile.folder_id == folder.id).order_by(func.lower(RoomFile.name)).all()
    return PublicFolderOut(
        name=folder.name,
        files=[PublicFolderFile(id=f.id, name=f.name, kind=f.kind, mime=f.mime, size=f.size) for f in files],
    )


@router.get(
    "/public/folders/{token}/files/{file_id}",
    dependencies=[Depends(limit_by_ip("public_folder_file", 30, 3600))],
)
def public_folder_file_download(token: str, file_id: int, db: Session = Depends(get_db)):
    """Same no-login model as /public/files/{token}, but re-checks that the file is STILL in this exact
    shared folder before serving it -- moving a file out, or turning the folder's link off, locks it
    immediately, even though the file row itself never changes."""
    folder = db.query(RoomFolder).filter(RoomFolder.share_token == token).first()
    if folder is None:
        raise _not_found("Folder")
    f = db.query(RoomFile).filter(RoomFile.id == file_id, RoomFile.folder_id == folder.id).first()
    if f is None:
        raise _not_found()
    return Response(
        content=_bytes_of(f),
        media_type="application/octet-stream",
        headers={"Content-Disposition": _disposition(f.name), "X-Content-Type-Options": "nosniff"},
    )

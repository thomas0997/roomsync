"""Profile photos. Thomas's file.

Safety rule: we NEVER store or serve what the user uploaded. The upload is decoded with Pillow, checked
(real JPEG/PNG/WebP, size and pixel limits), cropped to a square and re-drawn as a brand-new 256x256 JPEG.
Anything hidden in the original (scripts, EXIF/GPS data, extra bytes after the image) is thrown away.
The file is served with a fixed image type, and only to the owner and people who share a room with them."""
import io
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from PIL import Image, ImageOps
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..auth import get_current_user
from ..db import get_db
from ..models import Membership, User, UserAvatar, utcnow
from ..ratelimit import limit_by_user
from ..schemas import AvatarOut

router = APIRouter(prefix="/users", tags=["avatar"])

MAX_BYTES = 2 * 1024 * 1024        # biggest upload we read (2 MB)
MAX_PIXELS = 25_000_000            # width x height; stops "image bombs" (tiny file, enormous picture)
SIZE = 256                         # stored picture is SIZE x SIZE
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}  # decided by the file's CONTENT, never its name or Content-Type
BAD_IMAGE = "That file is not a valid JPEG, PNG or WebP photo."

Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # Pillow's own bomb guard as a second line of defence


async def read_limited_body(request: Request) -> bytes:
    """Read the request body, but stop as soon as it is over the limit (never load a huge upload)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Photo is too big (2 MB maximum).")
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Photo is too big (2 MB maximum).")
        chunks.append(chunk)
    return b"".join(chunks)


def make_avatar(raw: bytes) -> bytes:
    """Turn an uploaded file into a clean 256x256 JPEG, or raise 422 if it is not a real photo."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.format not in ALLOWED_FORMATS:
                raise ValueError("format not allowed")
            width, height = img.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise ValueError("bad size")
            img.load()                                   # decode everything now; a broken file fails here
            img = ImageOps.exif_transpose(img)           # respect the phone's rotation
            if img.mode in ("RGBA", "LA") or "transparency" in img.info:
                rgba = img.convert("RGBA")               # see-through areas become white
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                img = flat
            else:
                img = img.convert("RGB")
            img = ImageOps.fit(img, (SIZE, SIZE), Image.Resampling.LANCZOS)  # centre-crop to a square
            out = io.BytesIO()
            img.save(out, "JPEG", quality=85, optimize=True)  # no exif/icc passed in: metadata is dropped
            return out.getvalue()
    except Exception:  # any decoding problem means "not a valid photo"; we never log the file
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, BAD_IMAGE)


def _version(updated_at) -> int:
    if updated_at.tzinfo is None:  # SQLite drops the time zone
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return int(updated_at.timestamp())


def _url(user_id: int, updated_at) -> str:
    return f"/users/{user_id}/avatar?v={_version(updated_at)}"  # v changes when the photo changes


def avatar_url_for(db: Session, user_id: int) -> str | None:
    row = db.query(UserAvatar.updated_at).filter(UserAvatar.user_id == user_id).first()
    return _url(user_id, row[0]) if row else None


def avatar_urls_for(db: Session, user_ids: list[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.query(UserAvatar.user_id, UserAvatar.updated_at).filter(UserAvatar.user_id.in_(user_ids)).all()
    return {uid: _url(uid, ts) for uid, ts in rows}


@router.put(
    "/me/avatar",
    response_model=AvatarOut,
    dependencies=[Depends(limit_by_user("avatar", 10, 3600))],
)
def upload_avatar(
    raw: bytes = Depends(read_limited_body),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The body is the raw image file (not a form). Replaces my photo."""
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, BAD_IMAGE)
    data = make_avatar(raw)
    row = db.get(UserAvatar, user.id)
    if row is None:
        row = UserAvatar(user_id=user.id, data=data, updated_at=utcnow())
        db.add(row)
    else:
        row.data, row.updated_at = data, utcnow()
    db.commit()
    db.refresh(row)
    return AvatarOut(avatar_url=_url(user.id, row.updated_at))


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
def delete_avatar(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(UserAvatar).filter(UserAvatar.user_id == user.id).delete()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}/avatar")
def get_avatar(user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The photo of me, or of someone who shares a room with me. Anyone else gets the same 404
    as "no photo", so nobody can probe which users exist."""
    not_found = HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    if user_id != user.id:
        mine = db.query(Membership.room_id).filter(Membership.user_id == user.id)
        shared = (
            db.query(Membership.id)
            .filter(Membership.user_id == user_id, Membership.room_id.in_(mine))
            .first()
        )
        if shared is None:
            raise not_found
    row = db.get(UserAvatar, user_id)
    if row is None:
        raise not_found
    return Response(
        content=row.data,
        media_type="image/jpeg",  # fixed: never taken from the upload
        headers={"Content-Disposition": 'inline; filename="avatar.jpg"'},
    )
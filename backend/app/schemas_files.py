"""Request/response shapes for room files (Notes). Separate file so we don't collide in schemas.py."""
from datetime import datetime, timezone

from pydantic import BaseModel, field_serializer


class FileOut(BaseModel):
    id: int
    room_id: int
    name: str
    kind: str  # "docs" | "sheets" | "files"
    mime: str
    size: int
    locked: bool  # locking arrives later; always false for now
    created_by: int
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    updated_by_name: str
    version: int  # new versions arrive later; always 1 for now

    @field_serializer("created_at", "updated_at")
    def as_utc_z(self, value: datetime):
        # SQLite drops the timezone, so we re-attach UTC and print it as "...Z" like the contract says
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FileTextOut(BaseModel):
    name: str
    text: str
    truncated: bool  # true when the file is longer than the preview

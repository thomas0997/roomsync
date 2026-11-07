"""Request/response shapes for room messages. Separate file so we don't collide with Thomas in schemas.py."""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class MessageCreate(BaseModel):
    # forbid = reject unknown fields, so a client can't send author_id, room_id or created_at
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=2000)  # trimmed first, so "   " is empty and gives 422
    reply_to_id: int | None = Field(default=None, ge=1)
    # Clip attachments (T2): up to 5 existing room files, same rule as task attachments.
    file_ids: list[int] | None = Field(default=None, max_length=5)


class ReplyToOut(BaseModel):
    author_name: str
    snippet: str  # the first 80 characters of the message being replied to


class MessageAttachmentOut(BaseModel):
    file_id: int
    name: str
    size: int


class MessageOut(BaseModel):
    id: int
    room_id: int
    author_id: int
    author_name: str
    body: str
    reply_to_id: int | None
    reply_to: ReplyToOut | None
    created_at: datetime
    mentions: list[int] = []  # user ids whose @Full Name appears in body (computed on read, not stored)
    attachments: list[MessageAttachmentOut] = []  # oldest-attached first; names only, no file contents

    @field_serializer("created_at")
    def as_utc_z(self, value: datetime):
        # SQLite drops the timezone, so we re-attach UTC and print it as "...Z" like the contract says
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UnreadCountOut(BaseModel):
    count: int


class SeenByOut(BaseModel):
    user_id: int
    name: str
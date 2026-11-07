"""Request/response shapes for the Inbox (see docs/api-contract.md, "Inbox")."""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


def _clean(value: str) -> str:
    """Trim, and refuse text that is empty or only spaces."""
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class InboxSend(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    to_user_id: int = Field(ge=1)  # a syncmate picked from GET /inbox/syncmates
    subject: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("subject", "body")
    @classmethod
    def not_blank(cls, v):
        return _clean(v)


class InboxReply(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def not_blank(cls, v):
        return _clean(v)


class InboxArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archived: bool


class MessageOut(BaseModel):
    id: int
    from_user_id: int
    from_name: str
    to_user_id: int
    to_name: str
    subject: str
    body: str
    created_at: datetime
    read_at: datetime | None = None
    reply_to_id: int | None = None
    archived: bool = False

    @field_serializer("created_at", "read_at")
    def as_utc_z(self, value: datetime | None):
        if value is None:
            return None
        if value.tzinfo is None:  # SQLite drops the time zone
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UnreadOut(BaseModel):
    count: int


class SyncmateOut(BaseModel):
    """Someone who shares at least one room with me: name and the shared room names, never an email."""
    user_id: int
    name: str
    rooms: list[str]

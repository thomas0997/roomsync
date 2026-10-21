"""Request/response shapes for tasks. Separate file so we don't collide with Thomas in schemas.py."""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("must include a time zone, e.g. 2026-08-13T15:59:00Z")
    return value.astimezone(timezone.utc)


class TaskCreate(BaseModel):
    # forbid = reject unknown fields, so a client can't sneak in "status": "approved"
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=30)
    subject: str | None = Field(default=None, max_length=50)
    due_at: datetime  # REQUIRED (Thomas's decision, Oct 19): no default means a missing due_at gives 422
    all_day: bool = False

    @field_validator("subject")
    @classmethod
    def blank_subject_is_none(cls, v):
        return v or None

    @field_validator("due_at")
    @classmethod
    def due_at_to_utc(cls, v):
        return _to_utc(v)


class TaskUpdate(BaseModel):
    """PATCH body: every field is optional, but at least one must be sent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, min_length=1, max_length=30)
    subject: str | None = Field(default=None, max_length=50)  # null or "" clears the subject
    due_at: datetime | None = None
    all_day: bool | None = None

    @field_validator("subject")
    @classmethod
    def blank_subject_is_none(cls, v):
        return v or None

    @field_validator("due_at")
    @classmethod
    def due_at_to_utc(cls, v):
        return _to_utc(v)

    @model_validator(mode="after")
    def check_fields(self):
        sent = self.model_fields_set  # the fields the client actually sent
        if not sent:
            raise ValueError("send at least one field to change")
        for name in ("title", "type", "due_at", "all_day"):
            if name in sent and getattr(self, name) is None:  # only subject may be null
                raise ValueError(f"{name} cannot be null")
        return self


class TaskOut(BaseModel):
    id: int
    room_id: int
    title: str
    type: str
    subject: str | None
    due_at: datetime | None
    all_day: bool
    status: str
    created_by: int
    created_by_name: str
    decided_by_name: str | None
    decided_at: datetime | None
    done: bool = False  # ticked off by the CURRENT user (per-user, never shared)

    @field_serializer("due_at", "decided_at")
    def as_utc_z(self, value: datetime | None):
        # SQLite drops the timezone, so we re-attach UTC and print it as "...Z" like the contract says
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
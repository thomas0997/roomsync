"""Request/response shapes (what the frontend sends and receives)."""
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

# Presence (T2): a user counts as "online" if the server saw them (POST /presence/ping) in this window.
ONLINE_WINDOW = timedelta(minutes=2)

# The six built-in task types a user can recolor from Settings (see UserSettings.task_colors).
BUILTIN_TASK_TYPES = {"exam", "quiz", "case-study", "activity", "seatwork", "assignment"}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def is_online(user) -> bool:
    if user.last_seen is None:
        return False
    last_seen = user.last_seen
    if last_seen.tzinfo is None:  # SQLite hands back naive datetimes
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_seen <= ONLINE_WINDOW


class SignupIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v):
        # bcrypt can't hash more than 72 BYTES (emoji and accents use several bytes per character)
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password is too long (72 bytes at most)")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_fits_bcrypt(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password is too long (72 bytes at most)")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    name: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


RoomType = Literal["classroom", "study_group", "team", "other"]


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: RoomType = "classroom"


class RoomUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: RoomType | None = None

    @model_validator(mode="after")
    def _need_one_field(self):
        if self.name is None and self.type is None:
            raise ValueError("Send at least one of: name, type")
        return self


class RoomJoin(BaseModel):
    invite_code: str = Field(min_length=4, max_length=16)


class RoomOut(BaseModel):
    id: int
    name: str
    type: str
    invite_code: str | None  # only admins get the code; members get null
    role: str  # the caller's role in this room
    member_count: int
    pending_count: int  # tasks waiting for an admin decision
    avatar_url: str | None = None  # the room icon, null = default icon

class StatusOut(BaseModel):
    kind: str
    text: str | None = None


def status_of(user) -> StatusOut:
    return StatusOut(kind=user.status_kind or "working", text=user.status_text)


class MemberOut(BaseModel):
    user_id: int
    name: str
    role: str
    status: StatusOut | None = None
    online: bool = False  # T2: seen (POST /presence/ping) in the last 2 minutes
    avatar_url: str | None = None  # null when the member has no photo
    joined_at: datetime


class RoleIn(BaseModel):
    role: Literal["admin", "member"]


class InviteCodeOut(BaseModel):
    invite_code: str


StatusKind = Literal["working", "brb", "away", "custom"]


class AvatarOut(BaseModel):
    avatar_url: str


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    room: str | None = Field(default=None, max_length=100)
    rating: int = Field(ge=1, le=5)
    message: str = Field(min_length=1, max_length=2000)
    website: str | None = Field(default=None, max_length=500)  # hidden bot trap: people leave it empty


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    message: str = Field(min_length=1, max_length=2000)
    website: str | None = Field(default=None, max_length=500)  # hidden bot trap: people leave it empty


class ProfileOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    avatar_url: str | None = None  # null when there is no photo
    status: StatusOut
    joined_at: datetime


class SharedRoomOut(BaseModel):
    id: int
    name: str


class PublicProfileOut(BaseModel):
    """What a room-mate can see about someone: no email, only the rooms the two of them share."""
    id: int
    name: str
    avatar_url: str | None = None  # null when there is no photo
    status: StatusOut
    joined_at: datetime
    rooms: list[SharedRoomOut]


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status_kind: StatusKind | None = None
    status_text: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _need_one_field(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one of: name, status_kind, status_text")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        if "status_kind" in self.model_fields_set and self.status_kind is None:
            raise ValueError("status_kind cannot be null")
        return self


class StatsOut(BaseModel):
    submitted: int
    approved: int
    rejected: int


class HistoryItemOut(BaseModel):
    """One of your own submitted tasks, for the Profile > History table."""
    id: int
    title: str
    room_id: int
    room_name: str
    type: str
    status: str  # pending | approved | rejected
    created_at: datetime
    decided_at: datetime | None = None


Theme = Literal["light", "dark", "system"]


class SettingsOut(BaseModel):
    theme: Theme = "system"
    show_empty_days: bool = False
    notify_deadline_reminders: bool = True
    notify_mentions: bool = True
    notify_approvals: bool = False
    timezone: str = "Asia/Manila"
    task_colors: dict[str, str] = Field(default_factory=dict)

    @staticmethod
    def from_row(row) -> "SettingsOut":
        if row is None:
            return SettingsOut()
        try:
            colors = json.loads(row.task_colors or "{}")
        except ValueError:
            colors = {}
        return SettingsOut(
            theme=row.theme, show_empty_days=row.show_empty_days,
            notify_deadline_reminders=row.notify_deadline_reminders,
            notify_mentions=row.notify_mentions, notify_approvals=row.notify_approvals,
            timezone=row.timezone, task_colors=colors if isinstance(colors, dict) else {},
        )


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Theme | None = None
    show_empty_days: bool | None = None
    notify_deadline_reminders: bool | None = None
    notify_mentions: bool | None = None
    notify_approvals: bool | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=50)
    task_colors: dict[str, str] | None = None

    @field_validator("task_colors")
    @classmethod
    def _check_colors(cls, v):
        if v is None:
            return v
        bad_type = [t for t in v if t not in BUILTIN_TASK_TYPES]
        if bad_type:
            raise ValueError(f"Unknown task type(s): {', '.join(sorted(bad_type))}")
        bad_color = [t for t, c in v.items() if not HEX_COLOR.match(c)]
        if bad_color:
            raise ValueError("Colors must look like #rrggbb")
        return v

    @model_validator(mode="after")
    def _need_one_field(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one setting to change")
        return self
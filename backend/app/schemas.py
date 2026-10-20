"""Request/response shapes (what the frontend sends and receives)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


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
    joined_at: datetime


class RoleIn(BaseModel):
    role: Literal["admin", "member"]


class InviteCodeOut(BaseModel):
    invite_code: str


StatusKind = Literal["working", "brb", "away", "custom"]


class ProfileOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    avatar_url: str | None = None  # T2
    status: StatusOut
    joined_at: datetime


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
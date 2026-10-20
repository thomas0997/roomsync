"""Request/response shapes (what the frontend sends and receives)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class SignupIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


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

class MemberOut(BaseModel):
    user_id: int
    name: str
    role: str
    joined_at: datetime


class RoleIn(BaseModel):
    role: Literal["admin", "member"]


class InviteCodeOut(BaseModel):
    invite_code: str
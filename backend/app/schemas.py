"""Request/response shapes (what the frontend sends and receives)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RoomJoin(BaseModel):
    invite_code: str = Field(min_length=4, max_length=16)


class RoomOut(BaseModel):
    id: int
    name: str
    invite_code: str
    role: str  # the caller's role in this room
    member_count: int


class MemberOut(BaseModel):
    user_id: int
    name: str
    role: str
    joined_at: datetime

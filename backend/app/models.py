"""All database tables. Edit carefully: both of us touch this file, keep changes small."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    # status: "working" | "brb" | "away" | "custom". Never expires. status_text only used for "custom" (max 40).
    status_kind: Mapped[str] = mapped_column(String(10), default="working")
    status_text: Mapped[str | None] = mapped_column(String(40), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # soft delete
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")
    task_types = relationship("CustomTaskType", cascade="all, delete-orphan")


class UserAvatar(Base):
    """A user's profile photo: already shrunk to a 256x256 JPEG by the server (see routers/avatar.py).
    Own table so loading a User never loads the picture. One row per user; no row means no photo."""
    __tablename__ = "user_avatars"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20), default="classroom")  # classroom|study_group|team|other
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships = relationship("Membership", back_populates="room", cascade="all, delete-orphan")
    tasks = relationship("Task", cascade="all, delete-orphan")
    notes = relationship("Note", cascade="all, delete-orphan")
    messages = relationship("Message", cascade="all, delete-orphan")
    files = relationship("RoomFile", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "room_id", name="uq_user_room"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    role: Mapped[str] = mapped_column(String(10), default="member")  # "admin" | "member"
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="memberships")
    room = relationship("Room", back_populates="memberships")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(30))  # exam, quiz, case-study, ... or a custom type name
    subject: Mapped[str | None] = mapped_column(String(50), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|approved|rejected
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    approvals = relationship("Approval", cascade="all, delete-orphan")
    user_states = relationship("TaskUserState", cascade="all, delete-orphan")


class TaskUserState(Base):
    """Per-user view of a task: ticked off (done) and/or removed from that user's Home board (hidden).
    Nobody else sees these. One row per (user, task); the row is deleted when both flags are false."""
    __tablename__ = "task_user_state"
    __table_args__ = (UniqueConstraint("user_id", "task_id", name="uq_user_task_state"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class Approval(Base):
    # UNUSED: the first admin decision lives on Task (decided_by/decided_at). Remove in cleanup.
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("task_id", "voter_id", name="uq_task_voter"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(10))  # "approve" | "reject"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Note(Base):
    # UNUSED: replaced by Files (T2). Remove in cleanup.
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    reply_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomTaskType(Base):
    __tablename__ = "custom_task_types"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_typename"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(20))
    color: Mapped[str] = mapped_column(String(7))  # "#rrggbb"


class Feedback(Base):
    """A message from the About page's Feedback form (sent without logging in)."""
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    room: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1 to 5
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContactMessage(Base):
    """A message from the About page's Contact form (sent without logging in)."""
    __tablename__ = "contact_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoomFile(Base):
    """A file shared in a room's Notes (see routers/notes.py). The bytes are stored right here in `data`.
    `data` is deferred, so listing files never loads the file contents."""
    __tablename__ = "room_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))  # cleaned display name (never used as a path on disk)
    kind: Mapped[str] = mapped_column(String(10))  # "docs" | "sheets" | "files"
    mime: Mapped[str] = mapped_column(String(100))  # what the file is; it is always SERVED as a generic download
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

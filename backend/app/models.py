"""All database tables. Edit carefully: both of us touch this file, keep changes small."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
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
    # Presence (T2): set by POST /presence/ping, called every ~60s while a page is open.
    # "online" = last_seen within the last 2 minutes (see schemas.is_online). Never set means never online.
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # soft delete
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Goes up by one when the password is reset. Login tokens carry the number they were made with,
    # so every older login stops working the moment it changes.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")
    task_types = relationship("CustomTaskType", cascade="all, delete-orphan")


class PasswordReset(Base):
    """A "forgot password" link. We store only the SHA-256 hash of the secret (like a password),
    so a leaked database can't be used to reset anyone. One row per user at a time; works once."""
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserAvatar(Base):
    """A user's profile photo: already shrunk to a 256x256 JPEG by the server (see routers/avatar.py).
    Own table so loading a User never loads the picture. One row per user; no row means no photo."""
    __tablename__ = "user_avatars"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoomAvatar(Base):
    """A room's icon: a clean 256x256 JPEG made by the server (same pipeline as profile photos).
    Own table so loading a Room never loads the picture. No row means the default icon."""
    __tablename__ = "room_avatars"
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
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
    avatar = relationship("RoomAvatar", cascade="all, delete-orphan", uselist=False)


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
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)  # optional plain-text note
    edited_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # admin who edited it after approval
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    approvals = relationship("Approval", cascade="all, delete-orphan")
    user_states = relationship("TaskUserState", cascade="all, delete-orphan")
    attachment_links = relationship("TaskFile", cascade="all, delete-orphan")


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


class MessageFile(Base):
    """A note (room file) attached to a message via the clip icon, at most 5 per message
    (see routers/discussion.py). Deleting the message or the file removes the link; the other side stays."""
    __tablename__ = "message_files"
    __table_args__ = (UniqueConstraint("message_id", "file_id", name="uq_message_file"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("room_files.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageReadMarker(Base):
    """Per-user, per-room "I've read up to here" marker for Discussion (T2): backs unread counts and
    "seen by". One row per (user, room); created lazily, defaulting to the user's joined_at so history
    from before they joined is never counted as unread (see routers/discussion.py)."""
    __tablename__ = "message_read_markers"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomTaskType(Base):
    __tablename__ = "custom_task_types"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_typename"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(20))
    color: Mapped[str] = mapped_column(String(7))  # "#rrggbb"


class UserSettings(Base):
    """Account-level preferences (T2): docs/api-contract.md GET/PUT /users/me/settings.
    One row per user, created on first read or write (see routers/profile.py). `task_colors` overrides
    the color of the six built-in task types (never the badge text, never custom types)."""
    __tablename__ = "user_settings"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    theme: Mapped[str] = mapped_column(String(10), default="system", server_default="system")  # light|dark|system
    show_empty_days: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    notify_deadline_reminders: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    notify_mentions: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    notify_approvals: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Manila", server_default="Asia/Manila")
    task_colors: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")  # JSON: {"exam": "#rrggbb", ...}


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
    """A file shared in a room's Notes (see routers/notes.py). The bytes are in Cloudflare R2 (`storage_key` is set)
    or, for local development and files from before R2, right here in `data`.
    `data` is deferred, so listing files never loads the file contents."""
    __tablename__ = "room_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))  # cleaned display name (never used as a path on disk)
    kind: Mapped[str] = mapped_column(String(10))  # "docs" | "sheets" | "files"
    mime: Mapped[str] = mapped_column(String(100))  # what the file is; it is always SERVED as a generic download
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(200), nullable=True)  # set = bytes are in R2
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    task_links = relationship("TaskFile", cascade="all, delete-orphan")


class TaskFile(Base):
    """A note (room file) linked to a task, at most 5 per task (see routers/attachments.py).
    Deleting the task or the file removes the link; the other side stays."""
    __tablename__ = "task_files"
    __table_args__ = (UniqueConstraint("task_id", "file_id", name="uq_task_file"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("room_files.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InboxMessage(Base):
    """One private message between two room-mates (see routers/inbox.py). Plain text only.
    Each side has its own "removed" flag; the row is deleted for good when both have removed it.
    A message from a blocked sender is kept for the SENDER only (deleted_by_recipient=True), so the sender
    cannot tell it was blocked and the recipient never sees it."""
    __tablename__ = "inbox_messages"
    __table_args__ = (
        Index("ix_inbox_to_id", "to_user_id", "id"),
        Index("ix_inbox_from_id", "from_user_id", "id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    subject: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("inbox_messages.id", ondelete="SET NULL"), nullable=True
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # the recipient's archive
    deleted_by_sender: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    deleted_by_recipient: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class InboxBlock(Base):
    """`blocker_id` does not want messages from `blocked_id`."""
    __tablename__ = "inbox_blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_inbox_block"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    blocked_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

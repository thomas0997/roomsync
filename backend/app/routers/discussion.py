"""discussion endpoints. Owner: Daniel. Follow docs/api-contract.md exactly.
Never log message content."""
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_member
from ..db import get_db
from ..models import Membership, Message, MessageFile, MessageReadMarker, RoomFile, User, utcnow
from ..ratelimit import limit_by_user
from ..schemas_messages import (
    MessageAttachmentOut,
    MessageCreate,
    MessageOut,
    ReplyToOut,
    SeenByOut,
    UnreadCountOut,
)

router = APIRouter(tags=["discussion"])

SNIPPET_LENGTH = 80
MAX_ATTACHMENTS_PER_MESSAGE = 5


def _names(db: Session, user_ids: list[int]) -> dict[int, str]:
    """user id -> display name, in one query. Deleted users show as 'Deleted user'."""
    ids = list(set(user_ids))
    if not ids:
        return {}
    users = db.query(User).filter(User.id.in_(ids)).all()
    return {u.id: ("Deleted user" if u.deleted_at is not None else u.name) for u in users}


def _room_member_names(db: Session, room_id: int) -> dict[int, str]:
    """user id -> display name, for everyone currently in this room (for @mention matching)."""
    rows = (
        db.query(Membership.user_id, User.name)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.room_id == room_id)
        .all()
    )
    return {user_id: name for user_id, name in rows}


def _mentions(body: str, member_names: dict[int, str]) -> list[int]:
    """Which current room members are @mentioned in this text. Matches "@Full Name" on a word
    boundary; longest names are checked first so "Bob" can't shadow a match for "Bobby Lee".
    Computed fresh on every read, never stored, so a rename changes it for old messages too."""
    if "@" not in body:
        return []
    found = []
    for user_id, name in sorted(member_names.items(), key=lambda kv: -len(kv[1])):
        if not name:
            continue
        pattern = r"(?<!\w)@" + re.escape(name) + r"(?!\w)"
        if re.search(pattern, body):
            found.append(user_id)
    return found


def _attachments_by_message(db: Session, message_ids: list[int]) -> dict[int, list[MessageAttachmentOut]]:
    """message id -> its attached notes (oldest-attached first), in one query. Names only, no bytes."""
    if not message_ids:
        return {}
    rows = (
        db.query(MessageFile.message_id, RoomFile.id, RoomFile.name, RoomFile.size)
        .join(RoomFile, RoomFile.id == MessageFile.file_id)
        .filter(MessageFile.message_id.in_(message_ids))
        .order_by(MessageFile.id.asc())
        .all()
    )
    out: dict[int, list[MessageAttachmentOut]] = {}
    for message_id, file_id, name, size in rows:
        out.setdefault(message_id, []).append(MessageAttachmentOut(file_id=file_id, name=name, size=size))
    return out


def _to_out(db: Session, room_id: int, messages: list[Message]) -> list[MessageOut]:
    """Turn messages into API shapes, loading the replied-to messages, names, mentions and
    attachments in bulk (no N+1 queries for a page of messages)."""
    reply_ids = list({m.reply_to_id for m in messages if m.reply_to_id is not None})
    replied: dict[int, Message] = {}
    if reply_ids:
        replied = {r.id: r for r in db.query(Message).filter(Message.id.in_(reply_ids)).all()}
    names = _names(db, [m.author_id for m in messages] + [r.author_id for r in replied.values()])
    member_names = _room_member_names(db, room_id)
    attachments = _attachments_by_message(db, [m.id for m in messages])

    out = []
    for m in messages:
        parent = replied.get(m.reply_to_id) if m.reply_to_id is not None else None
        reply_to = None
        if parent is not None:
            reply_to = ReplyToOut(
                author_name=names.get(parent.author_id, "Deleted user"),
                snippet=parent.body[:SNIPPET_LENGTH],
            )
        out.append(
            MessageOut(
                id=m.id,
                room_id=m.room_id,
                author_id=m.author_id,
                author_name=names.get(m.author_id, "Deleted user"),
                body=m.body,
                reply_to_id=m.reply_to_id,
                reply_to=reply_to,
                created_at=m.created_at,
                mentions=_mentions(m.body, member_names),
                attachments=attachments.get(m.id, []),
            )
        )
    return out


def _get_or_create_marker(db: Session, user: User, room_id: int, membership: Membership) -> MessageReadMarker:
    marker = db.get(MessageReadMarker, (user.id, room_id))
    if marker is None:
        # First time we need it: treat them as caught up as of when they joined, so history
        # from before they joined is never counted as unread.
        marker = MessageReadMarker(user_id=user.id, room_id=room_id, last_read_at=membership.joined_at)
        db.add(marker)
        db.commit()
    return marker


@router.get("/rooms/{room_id}/messages", response_model=list[MessageOut])
def list_messages(
    room_id: int,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,  # 422 outside 1 to 100
    before_id: Annotated[int | None, Query(ge=1)] = None,  # leave it out for the latest page
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_member(db, user, room_id)  # 403 if not in this room

    query = db.query(Message).filter(Message.room_id == room_id)
    if before_id is not None:
        anchor = db.query(Message.id).filter(Message.id == before_id, Message.room_id == room_id).first()
        if anchor is None:  # unknown id, or a message from another room: nothing to page back from
            return []
        query = query.filter(Message.id < before_id)

    page = query.order_by(Message.id.desc()).limit(limit).all()  # newest first, to take the latest page
    page.reverse()  # the API returns oldest first
    return _to_out(db, room_id, page)


@router.post(
    "/rooms/{room_id}/messages",
    response_model=MessageOut,
    status_code=201,
    dependencies=[Depends(limit_by_user("post_message", 30, 60))],
)
def post_message(
    room_id: int,
    data: MessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_member(db, user, room_id)  # 403 if not in this room

    if data.reply_to_id is not None:
        parent = (
            db.query(Message)
            .filter(Message.id == data.reply_to_id, Message.room_id == room_id)
            .first()
        )
        if parent is None:  # missing, or in another room
            raise HTTPException(422, "reply_to_id must be a message in this room")

    file_ids = list(dict.fromkeys(data.file_ids or []))  # no duplicates, order kept
    if file_ids:  # every clip must be a file of THIS room (a missing file and another room's file look the same)
        found = db.query(RoomFile.id).filter(RoomFile.id.in_(file_ids), RoomFile.room_id == room_id).count()
        if found != len(file_ids):
            raise HTTPException(422, "One of the files was not found in this room")

    message = Message(room_id=room_id, author_id=user.id, body=data.body, reply_to_id=data.reply_to_id)
    db.add(message)
    db.commit()
    db.refresh(message)
    for file_id in file_ids:
        db.add(MessageFile(message_id=message.id, file_id=file_id))
    if file_ids:
        db.commit()
    return _to_out(db, room_id, [message])[0]


@router.delete("/messages/{message_id}", status_code=204)
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Addressed by message id, so 'no such message' and 'not in your room' give the same 404.
    not_found = HTTPException(404, "Message not found")
    message = db.get(Message, message_id)
    if message is None:
        raise not_found
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user.id, Membership.room_id == message.room_id)
        .first()
    )
    if membership is None:
        raise not_found

    if message.author_id != user.id:  # only the author, not even a room admin
        raise HTTPException(403, "You can only delete your own messages")

    # Replies to this message stay, but lose their link (SQLite does not do this by itself).
    db.query(Message).filter(Message.reply_to_id == message.id).update(
        {"reply_to_id": None}, synchronize_session=False
    )
    db.query(MessageFile).filter(MessageFile.message_id == message.id).delete(synchronize_session=False)
    db.delete(message)
    db.commit()
    return Response(status_code=204)


@router.get("/rooms/{room_id}/messages/unread-count", response_model=UnreadCountOut)
def unread_count(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = require_member(db, user, room_id)  # 403 if not in this room
    marker = _get_or_create_marker(db, user, room_id, membership)
    count = (
        db.query(Message)
        .filter(
            Message.room_id == room_id,
            Message.created_at > marker.last_read_at,
            Message.author_id != user.id,  # your own messages never count as unread for you
        )
        .count()
    )
    return UnreadCountOut(count=count)


@router.post(
    "/rooms/{room_id}/messages/read",
    status_code=204,
    dependencies=[Depends(limit_by_user("messages_read", 120, 60))],
)
def mark_read(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = require_member(db, user, room_id)  # 403 if not in this room
    marker = _get_or_create_marker(db, user, room_id, membership)
    marker.last_read_at = utcnow()
    db.commit()
    return Response(status_code=204)


@router.get("/rooms/{room_id}/messages/seen", response_model=list[SeenByOut])
def seen_by(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_member(db, user, room_id)  # 403 if not in this room
    latest = db.query(Message).filter(Message.room_id == room_id).order_by(Message.id.desc()).first()
    if latest is None:
        return []
    rows = (
        db.query(MessageReadMarker.user_id, User.name)
        .join(User, User.id == MessageReadMarker.user_id)
        .join(Membership, (Membership.user_id == MessageReadMarker.user_id) & (Membership.room_id == room_id))
        .filter(
            MessageReadMarker.room_id == room_id,
            MessageReadMarker.last_read_at >= latest.created_at,
            MessageReadMarker.user_id != user.id,
        )
        .all()
    )
    return [SeenByOut(user_id=uid, name=name) for uid, name in rows]
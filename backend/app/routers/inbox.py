"""Inbox: private one-to-one messages between room-mates. Thomas's file. Follows docs/api-contract.md ("Inbox").

Security rules (each one has a test in tests/test_inbox.py):
 - You can only write to someone who shares a room with you. An unknown email, a deleted account and a stranger all
   give the SAME 404, so nobody can find out who has an account.
 - Only the sender and the recipient can open a message. Everyone else, and a missing id, gets the same 404.
 - Never log message text, subjects or emails (this file has no logging at all).
 - Text is plain; the page shows it with textContent. No email address is ever returned, only names.
 - A blocked sender still gets a normal 201, but the recipient never sees the message.
 - Limits: 20 messages an hour, 100 a day, and 10 an hour to the same person (429)."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import InboxBlock, InboxMessage, Membership, User, utcnow
from ..ratelimit import hit, limit_by_user
from ..schemas_inbox import InboxArchive, InboxReply, InboxSend, MessageOut, UnreadOut

router = APIRouter(tags=["inbox"])

NO_CLASSMATE = "No classmate with that email in your rooms"
send_limits = [
    Depends(limit_by_user("inbox_send_hour", 20, 3600)),
    Depends(limit_by_user("inbox_send_day", 100, 86400)),
]


def _msg_404() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")


def _shares_a_room(db: Session, a: int, b: int) -> bool:
    mine = select(Membership.room_id).where(Membership.user_id == a)
    return (
        db.query(Membership.id).filter(Membership.user_id == b, Membership.room_id.in_(mine)).first() is not None
    )


def _display_name(user: User | None) -> str:
    return "Deleted user" if user is None or user.deleted_at is not None else user.name


def _to_out(db: Session, rows: list[InboxMessage], viewer_id: int) -> list[MessageOut]:
    """Turn messages into JSON with two queries at most (the people involved), not one per message."""
    ids = {m.from_user_id for m in rows} | {m.to_user_id for m in rows}
    people = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    return [
        MessageOut(
            id=m.id, from_user_id=m.from_user_id, from_name=_display_name(people.get(m.from_user_id)),
            to_user_id=m.to_user_id, to_name=_display_name(people.get(m.to_user_id)),
            subject=m.subject, body=m.body, created_at=m.created_at, read_at=m.read_at,
            reply_to_id=m.reply_to_id, archived=m.archived if m.to_user_id == viewer_id else False,
        )
        for m in rows
    ]


def _visible_message(db: Session, user: User, message_id: int) -> InboxMessage:
    """The message, if I am its sender or recipient and have not removed it. Anything else: the same 404."""
    m = db.get(InboxMessage, message_id)
    if m is None:
        raise _msg_404()
    if m.from_user_id == user.id and not m.deleted_by_sender:
        return m
    if m.to_user_id == user.id and not m.deleted_by_recipient:
        return m
    raise _msg_404()


def _deliver(db: Session, sender: User, recipient: User, subject: str, body: str, reply_to_id: int | None) -> MessageOut:
    """Store one message. Used by both new messages and replies, so both follow the same rules."""
    hit("inbox_to_person", f"{sender.id}:{recipient.id}", 10, 3600)  # 10 an hour to the same person
    blocked = (
        db.query(InboxBlock.id)
        .filter(InboxBlock.blocker_id == recipient.id, InboxBlock.blocked_id == sender.id)
        .first()
        is not None
    )
    m = InboxMessage(
        from_user_id=sender.id, to_user_id=recipient.id, subject=subject, body=body, reply_to_id=reply_to_id,
        deleted_by_recipient=blocked,  # blocked: only the sender's Sent folder has it
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return _to_out(db, [m], sender.id)[0]


@router.post("/inbox", response_model=MessageOut, status_code=201, dependencies=send_limits)
def send_message(body: InboxSend, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    recipient = (
        db.query(User).filter(User.email == body.to_email.lower(), User.deleted_at.is_(None)).first()
    )
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASSMATE)
    if recipient.id == user.id:
        raise HTTPException(422, "You cannot write to yourself")
    if not _shares_a_room(db, user.id, recipient.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASSMATE)
    return _deliver(db, user, recipient, body.subject, body.body, None)


@router.post("/inbox/{message_id}/reply", response_model=MessageOut, status_code=201, dependencies=send_limits)
def reply(message_id: int, body: InboxReply, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    original = _visible_message(db, user, message_id)
    other_id = original.to_user_id if original.from_user_id == user.id else original.from_user_id
    other = db.get(User, other_id)
    if other is None or other.deleted_at is not None or not _shares_a_room(db, user.id, other.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASSMATE)
    subject = original.subject if original.subject.startswith("Re: ") else f"Re: {original.subject}"
    return _deliver(db, user, other, subject[:120], body.body, original.id)


@router.get("/inbox", response_model=list[MessageOut], dependencies=[Depends(limit_by_user("inbox_read", 600, 3600))])
def list_messages(
    folder: Literal["inbox", "sent", "archived"] = "inbox",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before_id: Annotated[int | None, Query(ge=1)] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(InboxMessage)
    if folder == "sent":
        q = q.filter(InboxMessage.from_user_id == user.id, InboxMessage.deleted_by_sender.is_(False))
    else:
        q = q.filter(
            InboxMessage.to_user_id == user.id,
            InboxMessage.deleted_by_recipient.is_(False),
            InboxMessage.archived.is_(folder == "archived"),
        )
    if before_id is not None:
        q = q.filter(InboxMessage.id < before_id)
    rows = q.order_by(InboxMessage.id.desc()).limit(limit).all()
    return _to_out(db, rows, user.id)


@router.get("/inbox/unread-count", response_model=UnreadOut, dependencies=[Depends(limit_by_user("inbox_unread", 600, 3600))])
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = (
        db.query(func.count(InboxMessage.id))
        .filter(
            InboxMessage.to_user_id == user.id,
            InboxMessage.deleted_by_recipient.is_(False),
            InboxMessage.archived.is_(False),
            InboxMessage.read_at.is_(None),
        )
        .scalar()
    )
    return UnreadOut(count=n or 0)


@router.get("/inbox/{message_id}", response_model=MessageOut, dependencies=[Depends(limit_by_user("inbox_read", 600, 3600))])
def open_message(message_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    m = _visible_message(db, user, message_id)
    if m.to_user_id == user.id and m.read_at is None:  # only the recipient opening it counts as reading
        m.read_at = utcnow()
        db.commit()
        db.refresh(m)
    return _to_out(db, [m], user.id)[0]


@router.patch("/inbox/{message_id}", response_model=MessageOut)
def archive_message(
    message_id: int, body: InboxArchive, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    m = _visible_message(db, user, message_id)
    if m.to_user_id != user.id:  # the sender cannot archive; same 404 as a stranger
        raise _msg_404()
    m.archived = body.archived
    db.commit()
    db.refresh(m)
    return _to_out(db, [m], user.id)[0]


@router.delete("/inbox/{message_id}", status_code=204)
def remove_message(message_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    m = _visible_message(db, user, message_id)
    if m.from_user_id == user.id:
        m.deleted_by_sender = True
    else:
        m.deleted_by_recipient = True
    if m.deleted_by_sender and m.deleted_by_recipient:  # both removed it: gone for good
        db.query(InboxMessage).filter(InboxMessage.reply_to_id == m.id).update({InboxMessage.reply_to_id: None})
        db.delete(m)
    db.commit()
    return Response(status_code=204)


def _can_block(db: Session, user: User, other_id: int) -> bool:
    """You may block someone you share a room with, or who has written to you. Otherwise: the same 404."""
    if other_id == user.id:
        return False
    other = db.get(User, other_id)
    if other is None:
        return False
    if _shares_a_room(db, user.id, other_id):
        return True
    return (
        db.query(InboxMessage.id)
        .filter(InboxMessage.from_user_id == other_id, InboxMessage.to_user_id == user.id)
        .first()
        is not None
    )


@router.put("/inbox/blocks/{user_id}", status_code=204, dependencies=[Depends(limit_by_user("inbox_block", 60, 3600))])
def block_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not _can_block(db, user, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    exists = (
        db.query(InboxBlock.id).filter(InboxBlock.blocker_id == user.id, InboxBlock.blocked_id == user_id).first()
    )
    if exists is None:
        db.add(InboxBlock(blocker_id=user.id, blocked_id=user_id))
        db.commit()
    return Response(status_code=204)


@router.delete("/inbox/blocks/{user_id}", status_code=204, dependencies=[Depends(limit_by_user("inbox_block", 60, 3600))])
def unblock_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(InboxBlock).filter(InboxBlock.blocker_id == user.id, InboxBlock.blocked_id == user_id).delete()
    db.commit()
    return Response(status_code=204)

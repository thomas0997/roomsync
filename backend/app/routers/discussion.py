"""discussion endpoints. Owner: Daniel. Follow docs/api-contract.md exactly.
Never log message content."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_member
from ..db import get_db
from ..models import Membership, Message, User
from ..ratelimit import limit_by_user
from ..schemas_messages import MessageCreate, MessageOut, ReplyToOut

router = APIRouter(tags=["discussion"])

SNIPPET_LENGTH = 80


def _names(db: Session, user_ids: list[int]) -> dict[int, str]:
    """user id -> display name, in one query. Deleted users show as 'Deleted user'."""
    ids = list(set(user_ids))
    if not ids:
        return {}
    users = db.query(User).filter(User.id.in_(ids)).all()
    return {u.id: ("Deleted user" if u.deleted_at is not None else u.name) for u in users}


def _to_out(db: Session, messages: list[Message]) -> list[MessageOut]:
    """Turn messages into API shapes, loading the replied-to messages and all names in bulk."""
    reply_ids = list({m.reply_to_id for m in messages if m.reply_to_id is not None})
    replied: dict[int, Message] = {}
    if reply_ids:
        replied = {r.id: r for r in db.query(Message).filter(Message.id.in_(reply_ids)).all()}
    names = _names(db, [m.author_id for m in messages] + [r.author_id for r in replied.values()])

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
            )
        )
    return out


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
    return _to_out(db, page)


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

    message = Message(room_id=room_id, author_id=user.id, body=data.body, reply_to_id=data.reply_to_id)
    db.add(message)
    db.commit()
    db.refresh(message)
    return _to_out(db, [message])[0]


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
    db.delete(message)
    db.commit()
    return Response(status_code=204)
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin, require_member
from ..db import get_db
from ..models import Membership, Room, RoomAvatar, Task, User, utcnow
from ..ratelimit import limit_by_user
from ..schemas import AvatarOut
from .avatar import BAD_IMAGE, _version, avatar_urls_for, make_avatar, read_limited_body
from ..schemas import InviteCodeOut, MemberOut, RoleIn, RoomCreate, RoomJoin, RoomOut, RoomUpdate, is_online, status_of

router = APIRouter(prefix="/rooms", tags=["rooms"])
ALPHABET = string.ascii_uppercase + string.digits

# Server-enforced limits (409). Tests lower these with monkeypatch.
MAX_ROOMS_PER_USER = 10
MAX_MEMBERS_PER_ROOM = 50


def _new_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(8))
        if not db.query(Room).filter(Room.invite_code == code).first():
            return code


def _room_out(room: Room, role: str, db: Session) -> RoomOut:
    count = db.query(Membership).filter(Membership.room_id == room.id).count()
    pending = db.query(Task).filter(Task.room_id == room.id, Task.status == "pending").count()
    return RoomOut(
        id=room.id,
        name=room.name,
        type=room.type,
        invite_code=room.invite_code if role == "admin" else None,
        role=role,
        member_count=count,
        pending_count=pending,
        avatar_url=_room_avatar_url(db, room.id),
    )


def _room_avatar_url(db: Session, room_id: int) -> str | None:
    row = db.query(RoomAvatar.updated_at).filter(RoomAvatar.room_id == room_id).first()
    return f"/rooms/{room_id}/avatar?v={_version(row[0])}" if row else None

def _check_room_limit(db: Session, user: User) -> None:
    if db.query(Membership).filter(Membership.user_id == user.id).count() >= MAX_ROOMS_PER_USER:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Room limit reached: you can be in at most {MAX_ROOMS_PER_USER} rooms. Leave one first.",
        )


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(data: RoomCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_room_limit(db, user)
    room = Room(name=data.name.strip(), type=data.type, invite_code=_new_code(db), created_by=user.id)
    db.add(room)
    db.flush()
    db.add(Membership(user_id=user.id, room_id=room.id, role="admin"))
    db.commit()
    db.refresh(room)
    return _room_out(room, "admin", db)


@router.get("", response_model=list[RoomOut])
def my_rooms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Membership).filter(Membership.user_id == user.id).all()
    return [_room_out(m.room, m.role, db) for m in rows]


@router.post("/join", response_model=RoomOut, dependencies=[Depends(limit_by_user("join_room", 10, 60))])  # stops invite-code guessing
def join_room(data: RoomJoin, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.invite_code == data.invite_code.strip().upper()).first()
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid invite code")
    existing = db.query(Membership).filter(Membership.user_id == user.id, Membership.room_id == room.id).first()
    if existing:
        return _room_out(room, existing.role, db)
    _check_room_limit(db, user)
    if db.query(Membership).filter(Membership.room_id == room.id).count() >= MAX_MEMBERS_PER_ROOM:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This room is full ({MAX_MEMBERS_PER_ROOM} members).")
    db.add(Membership(user_id=user.id, room_id=room.id, role="member"))
    db.commit()
    return _room_out(room, "member", db)


@router.get("/{room_id}/members", response_model=list[MemberOut])
def members(room_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_member(db, user, room_id)
    rows = db.query(Membership).filter(Membership.room_id == room_id).all()
    photos = avatar_urls_for(db, [m.user_id for m in rows])
    return [
        MemberOut(user_id=m.user_id, name=m.user.name, role=m.role, joined_at=m.joined_at,
                  status=status_of(m.user), online=is_online(m.user), avatar_url=photos.get(m.user_id))
        for m in rows
    ]


@router.post("/{room_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_room(room_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    me = require_member(db, user, room_id)
    others = db.query(Membership).filter(Membership.room_id == room_id, Membership.user_id != user.id).all()
    if not others:  # last person out: delete the room and everything in it
        db.delete(db.get(Room, room_id))
    elif me.role == "admin" and not any(o.role == "admin" for o in others):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Promote another admin before leaving")
    else:
        db.delete(me)
    db.commit()


@router.post("/{room_id}/members/{user_id}/role", response_model=MemberOut)
def set_role(
    room_id: int,
    user_id: int,
    data: RoleIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(db, user, room_id)  # 403 unless the caller is an admin of this room
    target = db.query(Membership).filter(Membership.room_id == room_id, Membership.user_id == user_id).first()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    room = db.get(Room, room_id)

    if data.role == "member" and target.role == "admin":  # demoting
        if user.id != room.created_by:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the room creator can demote an admin")
        if target.user_id == room.created_by:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The room creator can't be demoted")
    # Promoting needs no extra check: any admin can promote (require_admin already ran).

    target.role = data.role
    db.commit()
    db.refresh(target)
    return MemberOut(
        user_id=target.user_id, name=target.user.name, role=target.role, joined_at=target.joined_at,
        status=status_of(target.user), online=is_online(target.user),
    )


@router.patch("/{room_id}", response_model=RoomOut)
def update_room(
    room_id: int,
    data: RoomUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    me = require_admin(db, user, room_id)
    room = db.get(Room, room_id)
    if data.name is not None:
        room.name = data.name.strip()
    if data.type is not None:
        room.type = data.type
    db.commit()
    db.refresh(room)
    return _room_out(room, me.role, db)


@router.delete("/{room_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    room_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(db, user, room_id)
    target = db.query(Membership).filter(Membership.room_id == room_id, Membership.user_id == user_id).first()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    room = db.get(Room, room_id)
    if target.user_id == room.created_by:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The room creator can't be removed")
    if target.role == "admin" and user.id != room.created_by:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the room creator can remove an admin")
    db.delete(target)
    db.commit()


@router.post("/{room_id}/invite-code/reset", response_model=InviteCodeOut)
def reset_invite_code(room_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_admin(db, user, room_id)
    room = db.get(Room, room_id)
    room.invite_code = _new_code(db)
    db.commit()
    return InviteCodeOut(invite_code=room.invite_code)


@router.put(
    "/{room_id}/avatar",
    response_model=AvatarOut,
    dependencies=[Depends(limit_by_user("room_avatar", 10, 3600))],
)
def upload_room_avatar(
    room_id: int,
    raw: bytes = Depends(read_limited_body),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admin only. The body is the raw image file; it is re-drawn as a clean 256x256 JPEG."""
    require_admin(db, user, room_id)
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, BAD_IMAGE)
    data = make_avatar(raw)
    row = db.get(RoomAvatar, room_id)
    if row is None:
        row = RoomAvatar(room_id=room_id, data=data, updated_at=utcnow())
        db.add(row)
    else:
        row.data, row.updated_at = data, utcnow()
    db.commit()
    return AvatarOut(avatar_url=_room_avatar_url(db, room_id))


@router.delete("/{room_id}/avatar", status_code=status.HTTP_204_NO_CONTENT)
def delete_room_avatar(room_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_admin(db, user, room_id)
    db.query(RoomAvatar).filter(RoomAvatar.room_id == room_id).delete()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{room_id}/avatar")
def get_room_avatar(room_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Members only (403 otherwise). 404 when the room has no icon."""
    require_member(db, user, room_id)
    row = db.get(RoomAvatar, room_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No icon")
    return Response(
        content=row.data,
        media_type="image/jpeg",  # fixed: never taken from the upload
        headers={"Content-Disposition": 'inline; filename="room.jpg"'},
    )
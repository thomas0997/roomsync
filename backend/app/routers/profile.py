"""Profile endpoints: who am I, my status, my stats, delete my account. Follow docs/api-contract.md."""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Membership, Room, Task, User, UserAvatar
from ..schemas import ProfileOut, ProfileUpdate, StatsOut, status_of
from .avatar import avatar_url_for

router = APIRouter(prefix="/users", tags=["profile"])


def _profile(user: User, db: Session) -> ProfileOut:
    return ProfileOut(
        id=user.id, email=user.email, name=user.name, status=status_of(user), joined_at=user.created_at,
        avatar_url=avatar_url_for(db, user.id),
    )


@router.get("/me", response_model=ProfileOut)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _profile(user, db)


@router.patch("/me", response_model=ProfileOut)
def update_me(data: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sent = data.model_fields_set
    if "name" in sent:
        name = data.name.strip()
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "name cannot be empty")
        user.name = name
    if "status_kind" in sent or "status_text" in sent:
        kind = data.status_kind if "status_kind" in sent else (user.status_kind or "working")
        text = (data.status_text or "").strip() if "status_text" in sent else (user.status_text or "")
        if kind == "custom":
            if not text:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "status_text is required for a custom status")
            user.status_kind, user.status_text = "custom", text
        else:
            user.status_kind, user.status_text = kind, None  # text only exists for "custom"
    db.commit()
    db.refresh(user)
    return _profile(user, db)


@router.get("/me/stats", response_model=StatsOut)
def my_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = dict(
        db.query(Task.status, func.count(Task.id)).filter(Task.created_by == user.id).group_by(Task.status).all()
    )
    return StatsOut(
        submitted=sum(rows.values()), approved=rows.get("approved", 0), rejected=rows.get("rejected", 0)
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mine = db.query(Membership).filter(Membership.user_id == user.id).all()
    plan = []
    for m in mine:
        others = db.query(Membership).filter(Membership.room_id == m.room_id, Membership.user_id != user.id).all()
        if others and m.role == "admin" and not any(o.role == "admin" for o in others):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "You are the only admin of a room with other members. Promote another admin first."
            )
        plan.append((m, bool(others)))
    for m, has_others in plan:
        if has_others:
            db.delete(m)
        else:
            db.delete(db.get(Room, m.room_id))  # last person out: the room goes too
    db.query(UserAvatar).filter(UserAvatar.user_id == user.id).delete()  # the photo goes with the account
    # Soft delete: keep the row so their tasks and messages stay (shown as "Deleted user")
    user.name = "Deleted user"
    user.email = f"deleted-{user.id}@deleted.invalid"  # frees the real email for a new signup
    user.password_hash = "!" + secrets.token_hex(16)  # not a valid bcrypt hash: nobody can log in
    user.status_kind, user.status_text = "working", None
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()
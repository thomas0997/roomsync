"""tasks endpoints. Owner: Daniel. Follow docs/api-contract.md exactly.
Every room endpoint must call require_member(db, user, room_id) from ..auth first."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_member
from ..db import get_db
from ..models import Membership, Task, User
from ..schemas_tasks import TaskCreate, TaskOut

router = APIRouter(tags=["tasks"])


def _name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    u = db.get(User, user_id)
    if u is None or u.deleted_at is not None:
        return "Deleted user"
    return u.name


def task_to_out(db: Session, task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        room_id=task.room_id,
        title=task.title,
        type=task.type,
        subject=task.subject,
        due_at=task.due_at,
        all_day=task.all_day,
        status=task.status,
        created_by=task.created_by,
        created_by_name=_name(db, task.created_by),
        decided_by_name=_name(db, task.decided_by),
        decided_at=task.decided_at,
    )


@router.post("/rooms/{room_id}/tasks", response_model=TaskOut, status_code=201)
def create_task(
    room_id: int,
    body: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = require_member(db, user, room_id)  # 403 if not in this room

    status = "pending"
    if membership.role == "admin":
        admin_count = (
            db.query(Membership)
            .filter(Membership.room_id == room_id, Membership.role == "admin")
            .count()
        )
        if admin_count == 1:  # the only admin: nobody else could approve, so auto-approve
            status = "approved"

    task = Task(
        room_id=room_id,
        title=body.title,
        type=body.type,
        subject=body.subject,
        due_at=body.due_at,
        all_day=body.all_day,
        status=status,
        created_by=user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_to_out(db, task)
"""approvals endpoints. Owner: Daniel. Follow docs/api-contract.md exactly."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..db import get_db
from ..models import Membership, Task, User
from ..schemas_tasks import TaskOut
from .tasks import _task_and_membership, task_to_out

router = APIRouter(tags=["approvals"])


@router.get("/rooms/{room_id}/approvals", response_model=list[TaskOut])
def list_pending(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_admin(db, user, room_id)  # 403 unless the caller is an admin of this room
    tasks = (
        db.query(Task)
        .filter(Task.room_id == room_id, Task.status == "pending")
        .order_by(Task.created_at, Task.id)  # oldest first
        .all()
    )
    return [task_to_out(db, t) for t in tasks]


@router.get("/rooms/{room_id}/approvals/history", response_model=list[TaskOut])
def list_history(
    room_id: int,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,  # 422 outside 1 to 200
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_admin(db, user, room_id)  # 403 unless the caller is an admin of this room
    tasks = (
        db.query(Task)
        .filter(
            Task.room_id == room_id,
            Task.status.in_(("approved", "rejected")),
            Task.decided_by.is_not(None),  # auto-approved tasks have no decider, so they are skipped
        )
        .order_by(Task.decided_at.desc(), Task.id.desc())  # newest decision first
        .limit(limit)
        .all()
    )
    return [task_to_out(db, t) for t in tasks]


def _decide(db: Session, user: User, task_id: int, new_status: str) -> TaskOut:
    task, membership = _task_and_membership(db, user, task_id)  # 404 if missing or not in this room

    if membership.role != "admin":
        raise HTTPException(403, "Only room admins can approve or reject tasks")
    if task.status != "pending":
        raise HTTPException(409, "Task already decided")

    if task.created_by == user.id:  # deciding your own task
        admin_count = (
            db.query(Membership)
            .filter(Membership.room_id == task.room_id, Membership.role == "admin")
            .count()
        )
        if admin_count > 1:  # allowed only when you are the room's only admin (checked now, not at creation)
            raise HTTPException(403, "You cannot decide your own task while the room has another admin")

    # First decision is final: the UPDATE only matches while the task is still pending,
    # so if two admins click at the same moment, one wins and the other gets 409.
    changed = (
        db.query(Task)
        .filter(Task.id == task.id, Task.status == "pending")
        .update(
            {"status": new_status, "decided_by": user.id, "decided_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
    )
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "Task already decided")
    db.commit()
    db.refresh(task)
    return task_to_out(db, task)


@router.post("/tasks/{task_id}/approve", response_model=TaskOut)
def approve_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _decide(db, user, task_id, "approved")


@router.post("/tasks/{task_id}/reject", response_model=TaskOut)
def reject_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _decide(db, user, task_id, "rejected")
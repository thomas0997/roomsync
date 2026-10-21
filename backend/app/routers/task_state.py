"""Per-user task state: tick a task off (done) and remove it from your own Home board (hidden).
Nobody else sees either one. Separate file so we don't collide with Daniel's tasks.py."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_member
from ..db import get_db
from ..models import Task, TaskUserState, User
from ..schemas_tasks import TaskOut
from .tasks import _task_and_membership, tasks_to_out

router = APIRouter(tags=["task-state"])


def _approved_task(db: Session, user: User, task_id: int) -> Task:
    task, _ = _task_and_membership(db, user, task_id)  # 404 if missing or not in this room
    if task.status != "approved":
        raise HTTPException(409, "Task is not approved yet")
    return task


def _set_flag(db: Session, user: User, task: Task, flag: str, value: bool) -> TaskOut:
    """Set done or hidden for this user. The row is created on demand and deleted when both are false."""
    row = (
        db.query(TaskUserState)
        .filter(TaskUserState.user_id == user.id, TaskUserState.task_id == task.id)
        .first()
    )
    if row is None and value:
        row = TaskUserState(user_id=user.id, task_id=task.id, done=False, hidden=False)
        db.add(row)
    if row is not None:
        setattr(row, flag, value)
        if not row.done and not row.hidden:
            db.delete(row)
    db.commit()
    db.refresh(task)
    return tasks_to_out(db, user, [task])[0]


@router.put("/tasks/{task_id}/done", response_model=TaskOut)
def mark_done(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _set_flag(db, user, _approved_task(db, user, task_id), "done", True)


@router.delete("/tasks/{task_id}/done", response_model=TaskOut)
def unmark_done(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _set_flag(db, user, _approved_task(db, user, task_id), "done", False)


@router.put("/tasks/{task_id}/hidden", response_model=TaskOut)
def hide_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _set_flag(db, user, _approved_task(db, user, task_id), "hidden", True)


@router.delete("/tasks/{task_id}/hidden", response_model=TaskOut)
def restore_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _set_flag(db, user, _approved_task(db, user, task_id), "hidden", False)


@router.get("/rooms/{room_id}/tasks/removed", response_model=list[TaskOut])
def list_removed(room_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_member(db, user, room_id)  # 403 if not in this room
    tasks = (
        db.query(Task)
        .join(TaskUserState, TaskUserState.task_id == Task.id)
        .filter(
            TaskUserState.user_id == user.id,
            TaskUserState.hidden.is_(True),
            Task.room_id == room_id,
            Task.status == "approved",
        )
        .order_by(Task.due_at, Task.id)
        .all()
    )
    return tasks_to_out(db, user, tasks)
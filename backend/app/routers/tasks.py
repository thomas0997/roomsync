"""tasks endpoints. Owner: Daniel. Follow docs/api-contract.md exactly.
Every room endpoint must call require_member(db, user, room_id) from ..auth first."""
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_member
from ..db import get_db
from ..models import Membership, Task, TaskUserState, User
from ..schemas_tasks import TaskCreate, TaskOut, TaskUpdate
from ..ratelimit import limit_by_user

router = APIRouter(tags=["tasks"])

# A task cannot be due in the past (Thomas's decision, Oct 20). Only the test setup turns this off
# (tests/conftest.py), because many older tests use fixed dates; tests/test_tasks_future_only.py turns it on.
ALLOW_PAST_DUE = os.getenv("ALLOW_PAST_DUE", "false").lower() == "true"


def _reject_past(due_at: datetime) -> None:
    if not ALLOW_PAST_DUE and due_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "due_at must be in the future")


def _check_all_day(all_day: bool, due_at: datetime) -> None:
    """An all-day task is stored as 15:59:00Z (23:59 in Manila, the end of that day)."""
    if all_day:
        utc = due_at.astimezone(timezone.utc) if due_at.tzinfo else due_at  # SQLite gives naive UTC
        if (utc.hour, utc.minute, utc.second, utc.microsecond) != (15, 59, 0, 0):
            raise HTTPException(422, "All-day tasks must be due at 15:59:00Z (the end of the day in Manila)")

# Weeks and months use Manila time until the T2 timezone setting exists (Thomas's decision, Oct 19).
# The Philippines has no daylight saving, so a fixed UTC+8 offset is exact.
MANILA = timezone(timedelta(hours=8))


def _name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    u = db.get(User, user_id)
    if u is None or u.deleted_at is not None:
        return "Deleted user"
    return u.name


def task_to_out(db: Session, task: Task, done: bool = False) -> TaskOut:
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
        done=done,
    )


def _states_for(db: Session, user: User, task_ids: list[int]) -> dict[int, TaskUserState]:
    """The current user's done/hidden rows for these tasks, by task id."""
    if not task_ids:
        return {}
    rows = (
        db.query(TaskUserState)
        .filter(TaskUserState.user_id == user.id, TaskUserState.task_id.in_(task_ids))
        .all()
    )
    return {r.task_id: r for r in rows}


def tasks_to_out(db: Session, user: User, tasks: list[Task], hide_removed: bool = False) -> list[TaskOut]:
    """Turn tasks into JSON with the current user's `done` flag. hide_removed drops the tasks
    this user removed from their Home board (the calendar keeps showing them)."""
    states = _states_for(db, user, [t.id for t in tasks])
    out = []
    for t in tasks:
        st = states.get(t.id)
        if hide_removed and st is not None and st.hidden:
            continue
        out.append(task_to_out(db, t, done=bool(st and st.done)))
    return out


def _approved_between(
    db: Session, user: User, room_id: int, start: datetime, end: datetime, hide_removed: bool = False
) -> list[TaskOut]:
    """Approved tasks of one room due from start (included) up to end (not included), earliest first."""
    tasks = (
        db.query(Task)
        .filter(
            Task.room_id == room_id,
            Task.status == "approved",  # only approved tasks show on the board and calendar
            Task.due_at >= start,
            Task.due_at < end,
        )
        .order_by(Task.due_at, Task.id)
        .all()
    )
    return tasks_to_out(db, user, tasks, hide_removed=hide_removed)


def _task_and_membership(db: Session, user: User, task_id: int) -> tuple[Task, Membership]:
    """For endpoints addressed by task id (Thomas's decision, Oct 20): 'no such task' and
    'not a member of its room' both give the same 404, so task ids cannot be probed."""
    not_found = HTTPException(404, "Task not found")
    task = db.get(Task, task_id)
    if task is None:
        raise not_found
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user.id, Membership.room_id == task.room_id)
        .first()
    )
    if membership is None:
        raise not_found
    return task, membership


@router.post(
    "/rooms/{room_id}/tasks",
    response_model=TaskOut,
    status_code=201,
    dependencies=[Depends(limit_by_user("create_task", 20, 3600))],
)
def create_task(
    room_id: int,
    body: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = require_member(db, user, room_id)  # 403 if not in this room
    _reject_past(body.due_at)
    _check_all_day(body.all_day, body.due_at)

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


@router.get("/rooms/{room_id}/tasks", response_model=list[TaskOut])
def list_week_tasks(
    room_id: int,
    week_start: date,  # required query parameter; a missing or malformed date gives 422 automatically
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_member(db, user, room_id)  # 403 if not in this room

    if week_start.weekday() != 6:  # Python: Monday is 0, Sunday is 6
        raise HTTPException(422, "week_start must be a Sunday")

    # Sunday 00:00 Manila time, converted to UTC, up to (but not including) the next Sunday 00:00
    start = datetime.combine(week_start, time.min, tzinfo=MANILA).astimezone(timezone.utc)
    end = start + timedelta(days=7)
    return _approved_between(db, user, room_id, start, end, hide_removed=True)  # Home board hides removed tasks


@router.get("/rooms/{room_id}/calendar", response_model=list[TaskOut])
def list_month_tasks(
    room_id: int,
    month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")],  # required, shaped like 2026-08, else 422
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_member(db, user, room_id)  # 403 if not in this room

    year, month_number = int(month[:4]), int(month[5:])
    if not (1 <= month_number <= 12) or not (2000 <= year <= 2100):
        raise HTTPException(422, "month must look like YYYY-MM, with a real month")

    # 1st of the month 00:00 Manila time, up to (but not including) the 1st of the next month
    next_year, next_month = (year + 1, 1) if month_number == 12 else (year, month_number + 1)
    start = datetime(year, month_number, 1, tzinfo=MANILA).astimezone(timezone.utc)
    end = datetime(next_year, next_month, 1, tzinfo=MANILA).astimezone(timezone.utc)
    return _approved_between(db, user, room_id, start, end)  # the calendar still shows removed tasks


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task, membership = _task_and_membership(db, user, task_id)  # 404 if missing or not in this room

    if task.created_by != user.id and membership.role != "admin":  # Thomas's decision, Oct 21: admins can fix a task before deciding
        raise HTTPException(403, "Only the creator or a room admin can edit this task")
    if task.status != "pending":
        raise HTTPException(403, "Only pending tasks can be edited")
    if "due_at" in body.model_fields_set:  # only a new due date has to be in the future
        _reject_past(body.due_at)
    if "all_day" in body.model_fields_set or "due_at" in body.model_fields_set:  # check the final combination
        _check_all_day(
            body.all_day if "all_day" in body.model_fields_set else task.all_day,
            body.due_at if "due_at" in body.model_fields_set else task.due_at,
        )

    for field in body.model_fields_set:  # change only what the client sent; status is never touched
        setattr(task, field, getattr(body, field))
    db.commit()
    db.refresh(task)
    return task_to_out(db, task)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task, membership = _task_and_membership(db, user, task_id)  # 404 if missing or not in this room

    if task.created_by != user.id and membership.role != "admin":
        raise HTTPException(403, "Only the creator or a room admin can delete this task")

    db.delete(task)
    db.commit()
    return Response(status_code=204)
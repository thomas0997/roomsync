"""tasks endpoints. Owner: Daniel. Follow docs/api-contract.md exactly.
Every room endpoint must call require_member(db, user, room_id) from ..auth first."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_member
from ..db import get_db
from ..models import Membership, Task, User
from ..schemas_tasks import TaskCreate, TaskOut

router = APIRouter(tags=["tasks"])

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


def _approved_between(db: Session, room_id: int, start: datetime, end: datetime) -> list[TaskOut]:
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
    return [task_to_out(db, t) for t in tasks]


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
    return _approved_between(db, room_id, start, end)


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
    return _approved_between(db, room_id, start, end)
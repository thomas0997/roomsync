"""Attach notes (room files) to a task. Thomas's file. Follows docs/api-contract.md ("Note attachments").

 - Same room only: the file must belong to the task's room. A missing file and a file of another room give the same 404.
 - Who: the task's creator or a room admin. Pending and approved tasks only; a rejected task is closed (403).
 - At most 5 notes per task (409). 60 attach or unlink calls an hour per user (429).
 - Attaching never gives anyone new access: people still need to be in the room to see the task or download the file."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import RoomFile, TaskFile, User
from ..ratelimit import limit_by_user
from ..schemas_tasks import TaskOut
from .tasks import _task_and_membership, tasks_to_out

router = APIRouter(tags=["attachments"])

MAX_NOTES_PER_TASK = 5
rate = Depends(limit_by_user("task_attach", 60, 3600))


def _check_may_change(task, membership, user) -> None:
    if task.created_by != user.id and membership.role != "admin":
        raise HTTPException(403, "Only the creator or a room admin can change a task's notes")
    if task.status == "rejected":
        raise HTTPException(403, "Rejected tasks cannot be changed")


@router.put("/tasks/{task_id}/attachments/{file_id}", response_model=TaskOut, dependencies=[rate])
def attach_note(task_id: int, file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task, membership = _task_and_membership(db, user, task_id)  # 404 if missing or not in this room
    _check_may_change(task, membership, user)
    f = db.get(RoomFile, file_id)
    if f is None or f.room_id != task.room_id:  # missing and other-room look identical
        raise HTTPException(404, "File not found")
    links = db.query(TaskFile).filter(TaskFile.task_id == task.id).all()
    if all(link.file_id != file_id for link in links):  # linking twice is fine and changes nothing
        if len(links) >= MAX_NOTES_PER_TASK:
            raise HTTPException(409, "A task can have at most 5 notes")
        db.add(TaskFile(task_id=task.id, file_id=file_id))
        try:
            db.commit()
        except IntegrityError:  # a double click raced us; the link exists, which is what was asked
            db.rollback()
    return tasks_to_out(db, user, [task])[0]


@router.delete("/tasks/{task_id}/attachments/{file_id}", status_code=204, dependencies=[rate])
def detach_note(task_id: int, file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task, membership = _task_and_membership(db, user, task_id)
    _check_may_change(task, membership, user)
    db.query(TaskFile).filter(TaskFile.task_id == task.id, TaskFile.file_id == file_id).delete()
    db.commit()
    return Response(status_code=204)

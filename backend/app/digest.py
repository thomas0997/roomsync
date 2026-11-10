"""Deadline reminder digest: ONE email per user per day listing tasks due soon, instead of
three separate emails per task (see docs/api-contract.md "Deadline reminders", decided Nov 10
to stay well under Resend's free quota).

Runs once a day from the scheduler (app/scheduler.py). Can also be run by hand:
    python -m app.digest            # dry run: prints what WOULD be sent, sends nothing
    python -m app.digest --send     # actually sends (and marks users as sent-today)
"""
import hashlib
import hmac
import logging
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import mailer
from .auth import SECRET_KEY
from .db import SessionLocal
from .models import Membership, Room, Task, TaskUserState, User, UserSettings

log = logging.getLogger("roomsync.digest")

LOOKAHEAD_DAYS = 3


def unsubscribe_token(user_id: int) -> str:
    """Deterministic, never expires, needs no database row: HMAC(SECRET_KEY, "unsub:<id>").
    Lets an old digest email's unsubscribe link keep working indefinitely."""
    sig = hmac.new(SECRET_KEY.encode(), f"unsub:{user_id}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{user_id}.{sig}"


def verify_unsubscribe_token(token: str) -> int | None:
    """Returns the user_id if the token is valid, else None. Constant-time compare (hmac.compare_digest)."""
    try:
        uid_str, sig = token.split(".", 1)
        user_id = int(uid_str)
    except (ValueError, AttributeError):
        return None
    expected = unsubscribe_token(user_id)
    return user_id if hmac.compare_digest(expected, token) else None


def _eligible_users(db: Session, now: datetime) -> list[User]:
    """Verified, opted in, not deleted, and not already sent today (UTC calendar day -- the whole
    app is Manila-only for now, so this matches "today" closely enough without per-user timezone math)."""
    # Outer join: a user with no UserSettings row yet (lazily created on first read or write,
    # see models.py) still counts as opted in, since the column's own default is True.
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(User)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .filter(
            User.deleted_at.is_(None),
            User.email_verified.is_(True),
            or_(UserSettings.notify_deadline_reminders.is_(True), UserSettings.notify_deadline_reminders.is_(None)),
        )
        .filter((User.last_digest_sent_at.is_(None)) | (User.last_digest_sent_at < today_start))
        .all()
    )


def _due_soon_tasks(db: Session, user: User, now: datetime) -> list[Task]:
    """Approved tasks, due within LOOKAHEAD_DAYS, in any room this user is a member of, that
    THIS user has not ticked done. Not yet overdue (overdue tasks already show the ALERT look
    in the app itself, so the digest stays about what's still coming up)."""
    room_ids = [m.room_id for m in db.query(Membership.room_id).filter(Membership.user_id == user.id).all()]
    if not room_ids:
        return []
    window_end = now + timedelta(days=LOOKAHEAD_DAYS)
    done_task_ids = {
        row.task_id
        for row in db.query(TaskUserState.task_id)
        .filter(TaskUserState.user_id == user.id, TaskUserState.done.is_(True))
        .all()
    }
    tasks = (
        db.query(Task)
        .filter(
            Task.room_id.in_(room_ids),
            Task.status == "approved",
            Task.due_at.isnot(None),
            Task.due_at >= now,
            Task.due_at <= window_end,
        )
        .order_by(Task.due_at.asc())
        .all()
    )
    return [t for t in tasks if t.id not in done_task_ids]


def _format_digest(user: User, tasks: list[Task], room_names: dict[int, str]) -> str:
    lines = [
        f"Hi {mailer.one_line(user.name, 60)},",
        "",
        f"Here's what's due in your RoomSync rooms over the next {LOOKAHEAD_DAYS} days:",
        "",
    ]
    for t in tasks:
        when = "No specific time" if t.all_day else t.due_at.strftime("%b %d, %I:%M %p UTC")
        if t.all_day:
            when = t.due_at.strftime("%b %d") + " (all day)"
        lines.append(f"- [{room_names.get(t.room_id, 'Room')}] {t.title} ({t.type}) -- due {when}")
    lines += [
        "",
        f"Open RoomSync: {mailer.app_url()}",
        "",
        f"Don't want these? Unsubscribe any time: {mailer.app_url()}/unsubscribe?token={unsubscribe_token(user.id)}",
        "",
        "RoomSync",
    ]
    return "\n".join(lines)


def run_digest(db: Session, *, dry_run: bool = False, now: datetime | None = None) -> dict:
    """The whole job: find eligible users, build each one's digest, send it (unless dry_run),
    and mark who was sent today (unless dry_run). Returns stats for logging / manual runs."""
    now = now or datetime.now(timezone.utc)
    users = _eligible_users(db, now)
    room_names = {r.id: r.name for r in db.query(Room.id, Room.name).all()}
    emailed = 0
    skipped_nothing_due = 0
    for user in users:
        tasks = _due_soon_tasks(db, user, now)
        if not tasks:
            skipped_nothing_due += 1
            continue
        text = _format_digest(user, tasks, room_names)
        if dry_run:
            log.info("DRY RUN would email %s: %d task(s)", user.email, len(tasks))
        else:
            mailer.deliver(
                to=user.email,
                subject=f"RoomSync: {len(tasks)} task{'s' if len(tasks) != 1 else ''} due soon",
                text=text,
                kind="deadline_digest",
            )
            user.last_digest_sent_at = now
        emailed += 1
    if not dry_run:
        db.commit()
    stats = {"eligible": len(users), "emailed": emailed, "skipped_nothing_due": skipped_nothing_due}
    log.info("digest run: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    send = "--send" in sys.argv
    with SessionLocal() as session:
        result = run_digest(session, dry_run=not send)
    mode = "SENT" if send else "DRY RUN (pass --send to actually email)"
    print(f"{mode}: {result}")

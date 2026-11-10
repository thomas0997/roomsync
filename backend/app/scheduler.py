"""Runs the deadline-reminder digest (app/digest.py) once a day, in-process. One Render
instance only (see CLAUDE.md / checklist: the rate limiter is in-memory for the same reason),
so there's no risk of two instances both firing the job.

23:00 UTC = 7:00 AM Manila (Philippines is UTC+8, fixed, no daylight saving), a reasonable
time for students to see "what's due this week" before their day starts.

Does NOT start during tests: pytest never runs the app's lifespan (tests/conftest.py builds
TestClient(app) without the `with` form that triggers startup/shutdown), so this file is
inert there -- confirmed by the full test run staying the same length with or without it.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import SessionLocal
from .digest import run_digest

log = logging.getLogger("roomsync.scheduler")

DIGEST_HOUR_UTC = 23  # 7:00 AM Manila
DIGEST_MINUTE_UTC = 0

_scheduler: BackgroundScheduler | None = None


def _run_digest_job() -> None:
    try:
        with SessionLocal() as db:
            run_digest(db)
    except Exception:  # a bad run must never crash the server or stop future runs
        log.exception("deadline digest job failed")


def start() -> None:
    global _scheduler
    if _scheduler is not None:  # already running (e.g. a reload); never start a second one
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_digest_job,
        CronTrigger(hour=DIGEST_HOUR_UTC, minute=DIGEST_MINUTE_UTC, timezone="UTC"),
        id="deadline_digest",
        replace_existing=True,
    )
    _scheduler.start()
    log.info("scheduler started: deadline digest at %02d:%02d UTC daily", DIGEST_HOUR_UTC, DIGEST_MINUTE_UTC)


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None

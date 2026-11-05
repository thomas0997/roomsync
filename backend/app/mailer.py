"""Sending email through Resend. Thomas's file.

Rules: sending NEVER breaks a request (every problem is swallowed and only logged as a kind + ok/failed flag,
never the address or the text), and with no RESEND_API_KEY set (local dev, tests) nothing is sent.
Endpoints call it through FastAPI background tasks so the user never waits for Resend:

    background.add_task(mailer.deliver, to="a@b.c", subject="...", text="...", kind="password_reset")

Plain text only: that way nothing a user typed can ever turn into markup inside an email.
"""
import logging
import os

import httpx

log = logging.getLogger("roomsync.mailer")

RESEND_URL = "https://api.resend.com/emails"


def configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY"))


def app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:5500").rstrip("/")


def one_line(value: str, limit: int = 120) -> str:
    """Subjects and names go in headers: no line breaks allowed (stops header injection)."""
    return " ".join(str(value).split())[:limit]


def deliver(*, to: str, subject: str, text: str, kind: str, reply_to: str | None = None) -> bool:
    key = os.getenv("RESEND_API_KEY")
    if not key:
        return False
    payload = {
        "from": os.getenv("EMAIL_FROM", "RoomSync <no-reply@roomsync.me>"),
        "to": [to],
        "subject": one_line(subject, 200),
        "text": text,
    }
    reply = reply_to or os.getenv("EMAIL_REPLY_TO")
    if reply:
        payload["reply_to"] = reply
    try:
        r = httpx.post(
            RESEND_URL,
            json=payload,
            headers={"Authorization": f"Bearer {key}", "User-Agent": "roomsync-api/1.0"},
            timeout=10,
        )
        ok = r.status_code == 200
    except Exception:  # network trouble, timeouts, anything: never break the request
        ok = False
    log.info("email kind=%s ok=%s", kind, ok)
    return ok

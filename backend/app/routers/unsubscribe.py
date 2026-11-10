"""GET /unsubscribe -- the one public endpoint for deadline-reminder digests (see
docs/api-contract.md "Deadline reminders"). No login needed: the link's token IS the proof,
same idea as the password-reset and email-verification links, except this one never expires
(see app/digest.py unsubscribe_token) so an old email's link keeps working.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..digest import verify_unsubscribe_token
from ..models import User, UserSettings
from ..ratelimit import limit_by_ip

router = APIRouter(tags=["unsubscribe"])

_OK_PAGE = "<!doctype html><html><body><p>You're unsubscribed from RoomSync deadline reminders.</p></body></html>"
_BAD_PAGE = "<!doctype html><html><body><p>That unsubscribe link isn't valid.</p></body></html>"


@router.get(
    "/unsubscribe",
    response_class=HTMLResponse,
    dependencies=[Depends(limit_by_ip("unsubscribe", 30, 3600))],
)
def unsubscribe(token: str, db: Session = Depends(get_db)):
    user_id = verify_unsubscribe_token(token)
    if user_id is None:
        return HTMLResponse(_BAD_PAGE, status_code=400)
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        # The signature is valid but the account is gone: nothing to turn off, same friendly page.
        return HTMLResponse(_OK_PAGE)
    settings = db.get(UserSettings, user_id)
    if settings is None:
        # No settings row yet (never saved any preference): create one, already opted out.
        settings = UserSettings(user_id=user_id, notify_deadline_reminders=False)
        db.add(settings)
    else:
        settings.notify_deadline_reminders = False
    db.commit()
    return HTMLResponse(_OK_PAGE)

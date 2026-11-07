"""Presence (T2): a lightweight heartbeat so "online" can be shown on the member list.
No body, no response body. The frontend calls this every ~60s while a page is open
(see js/sidebar_rooms.js); "online" is then computed as "seen in the last 2 minutes"
(see schemas.is_online), never stored as a flag."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User, utcnow
from ..ratelimit import limit_by_user

router = APIRouter(prefix="/presence", tags=["presence"])


@router.post(
    "/ping",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_user("presence_ping", 120, 60))],  # generous: one tab pings every ~60s
)
def ping(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.last_seen = utcnow()
    db.commit()

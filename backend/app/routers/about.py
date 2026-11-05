"""About page forms: Feedback and Contact. Thomas's file.

Both are public (no login), so they are rate-limited per address, and a hidden "website" field catches
bots: if it is filled in we answer 204 and save nothing. Messages are saved in the database for the team
to read. We never log what people write."""
import os

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from sqlalchemy.orm import Session

from .. import mailer
from ..db import get_db
from ..models import ContactMessage, Feedback
from ..ratelimit import limit_by_ip
from ..schemas import ContactIn, FeedbackIn

router = APIRouter(tags=["about"])


def _forward(background: BackgroundTasks, kind: str, subject: str, text: str, reply_to: str | None = None) -> None:
    """Also email the message to the team inbox (CONTACT_INBOX). Skipped when email isn't set up."""
    inbox = os.getenv("CONTACT_INBOX")
    if inbox and mailer.configured():
        background.add_task(mailer.deliver, to=inbox, subject=subject, text=text, kind=kind, reply_to=reply_to)


@router.post(
    "/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_ip("feedback", 5, 3600))],
)
def send_feedback(body: FeedbackIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not body.website:  # a filled-in trap field means a bot: pretend it worked, save nothing
        db.add(Feedback(name=body.name, room=body.room or None, rating=body.rating, message=body.message))
        db.commit()
        _forward(
            background, "feedback",
            f"RoomSync feedback ({body.rating}/5) from {mailer.one_line(body.name, 60)}",
            f"Name: {mailer.one_line(body.name)}\nRoom: {mailer.one_line(body.room or '-')}\nRating: {body.rating}/5\n\n{body.message}\n",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/contact",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_ip("contact", 5, 3600))],
)
def send_contact(body: ContactIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not body.website:
        db.add(ContactMessage(name=body.name, email=body.email, message=body.message))
        db.commit()
        _forward(
            background, "contact",
            f"RoomSync contact from {mailer.one_line(body.name, 60)}",
            f"Name: {mailer.one_line(body.name)}\nEmail: {body.email}\n\n{body.message}\n",
            reply_to=body.email,  # hitting Reply answers the visitor
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

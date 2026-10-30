"""About page forms: Feedback and Contact. Thomas's file.

Both are public (no login), so they are rate-limited per address, and a hidden "website" field catches
bots: if it is filled in we answer 204 and save nothing. Messages are saved in the database for the team
to read. We never log what people write."""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ContactMessage, Feedback
from ..ratelimit import limit_by_ip
from ..schemas import ContactIn, FeedbackIn

router = APIRouter(tags=["about"])


@router.post(
    "/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_ip("feedback", 5, 3600))],
)
def send_feedback(body: FeedbackIn, db: Session = Depends(get_db)):
    if not body.website:  # a filled-in trap field means a bot: pretend it worked, save nothing
        db.add(Feedback(name=body.name, room=body.room or None, rating=body.rating, message=body.message))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/contact",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_ip("contact", 5, 3600))],
)
def send_contact(body: ContactIn, db: Session = Depends(get_db)):
    if not body.website:
        db.add(ContactMessage(name=body.name, email=body.email, message=body.message))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

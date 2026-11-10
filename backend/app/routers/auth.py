import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .. import mailer
from ..auth import create_token, get_current_user, hash_password, verify_password
from ..db import get_db
from ..models import EmailVerification, PasswordReset, User
from ..ratelimit import hit, limit_by_ip, limit_by_user
from ..schemas import ForgotIn, LoginIn, ResetIn, SignupIn, TokenOut, UserOut, VerifyIn

RESET_MINUTES = 30
VERIFY_HOURS = 24

router = APIRouter(prefix="/auth", tags=["auth"])


def _send_verification_email(db, user: User, background: BackgroundTasks) -> None:
    """Shared by signup and /auth/resend-verification. A new link replaces any old one."""
    db.query(EmailVerification).filter(EmailVerification.user_id == user.id).delete()
    token = secrets.token_urlsafe(32)
    db.add(EmailVerification(
        user_id=user.id,
        token_hash=_hash_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=VERIFY_HOURS),
    ))
    db.commit()
    # The secret goes after the # so it never reaches server logs or the Referer header.
    link = f"{mailer.app_url()}/pages/verify.html#token={token}"
    background.add_task(
        mailer.deliver,
        to=user.email,
        subject="Confirm your RoomSync email",
        text=(
            f"Hi {mailer.one_line(user.name, 60)},\n\n"
            f"Confirm this is your email address so RoomSync can send you deadline reminders. "
            f"This link works for {VERIFY_HOURS} hours:\n\n{link}\n\n"
            "If you didn't sign up for RoomSync, you can ignore this email.\n\n"
            "RoomSync"
        ),
        kind="email_verification",
    )


@router.post(
    "/signup",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_by_ip("signup", 5, 3600))],  # 5 signups per hour per address
)
def signup(data: SignupIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email, name=data.name.strip(), password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    _send_verification_email(db, user, background)
    return TokenOut(access_token=create_token(user.id, user.token_version), user=user)


@router.post(
    "/login",
    response_model=TokenOut,
    dependencies=[Depends(limit_by_ip("login", 10, 60))],  # 10 tries per minute per address
)
def login(data: LoginIn, db: Session = Depends(get_db)):
    hit("login_email", data.email.lower(), 10, 900)  # and 10 tries per 15 min per account, whatever the address
    user = db.query(User).filter(User.email == data.email.lower()).first()
    # Same error for "no such user" and "wrong password" so attackers can't tell which
    if user is None or user.deleted_at is not None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return TokenOut(access_token=create_token(user.id, user.token_version), user=user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)  # SQLite drops the timezone


@router.post(
    "/forgot",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_ip("forgot", 5, 3600))],  # 5 per hour per address
)
def forgot(data: ForgotIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Always answers 204, so nobody can use this to find out which emails have accounts."""
    email = data.email.lower()
    hit("forgot_email", email, 3, 3600)  # and 3 per hour per email, whoever asks (stops inbox flooding)
    user = db.query(User).filter(User.email == email).first()
    if user is not None and user.deleted_at is None:
        db.query(PasswordReset).filter(PasswordReset.user_id == user.id).delete()  # a new link replaces the old one
        token = secrets.token_urlsafe(32)
        db.add(PasswordReset(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_MINUTES),
        ))
        db.commit()
        # The secret goes after the # so it never reaches server logs or the Referer header.
        link = f"{mailer.app_url()}/pages/reset.html#token={token}"
        background.add_task(
            mailer.deliver,
            to=user.email,
            subject="Reset your RoomSync password",
            text=(
                f"Hi {mailer.one_line(user.name, 60)},\n\n"
                f"Someone asked to reset the password for your RoomSync account. "
                f"Open this link within {RESET_MINUTES} minutes to choose a new one:\n\n{link}\n\n"
                "If that wasn't you, ignore this email. Your password has not changed.\n\n"
                "RoomSync"
            ),
            kind="password_reset",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_ip("reset", 10, 3600))],  # 10 tries per hour per address
)
def reset_password(data: ResetIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    bad_link = HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired link")  # same words for every failure
    now = datetime.now(timezone.utc)
    row = db.query(PasswordReset).filter(PasswordReset.token_hash == _hash_token(data.token)).first()
    if row is None or row.used_at is not None or _aware(row.expires_at) <= now:
        raise bad_link
    user = db.get(User, row.user_id)
    if user is None or user.deleted_at is not None:
        raise bad_link
    # Claim the link first: if two requests race, only one of them gets rowcount 1.
    claimed = (
        db.query(PasswordReset)
        .filter(PasswordReset.id == row.id, PasswordReset.used_at.is_(None))
        .update({"used_at": now})
    )
    if claimed != 1:
        db.rollback()
        raise bad_link
    user.password_hash = hash_password(data.new_password)
    user.token_version += 1  # every older login stops working
    db.commit()
    background.add_task(
        mailer.deliver,
        to=user.email,
        subject="Your RoomSync password was changed",
        text=(
            f"Hi {mailer.one_line(user.name, 60)},\n\n"
            "The password for your RoomSync account was just changed, and you were logged out everywhere.\n\n"
            "If that was you, nothing else to do. If it wasn't, reset your password again right away "
            f"at {mailer.app_url()}/pages/login.html and reply to this email so we can help.\n\n"
            "RoomSync"
        ),
        kind="password_changed",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_ip("verify", 10, 3600))],  # 10 tries per hour per address
)
def verify_email(data: VerifyIn, db: Session = Depends(get_db)):
    bad_link = HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired link")  # same words for every failure
    now = datetime.now(timezone.utc)
    row = db.query(EmailVerification).filter(EmailVerification.token_hash == _hash_token(data.token)).first()
    if row is None or row.used_at is not None or _aware(row.expires_at) <= now:
        raise bad_link
    user = db.get(User, row.user_id)
    if user is None or user.deleted_at is not None:
        raise bad_link
    # Claim the link first: if two requests race, only one of them gets rowcount 1.
    claimed = (
        db.query(EmailVerification)
        .filter(EmailVerification.id == row.id, EmailVerification.used_at.is_(None))
        .update({"used_at": now})
    )
    if claimed != 1:
        db.rollback()
        raise bad_link
    user.email_verified = True
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/resend-verification",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_user("resend_verification", 3, 3600))],  # 3 per hour per account
)
def resend_verification(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Always 204, even if already verified, so the button never needs to explain itself."""
    if not user.email_verified:
        _send_verification_email(db, user, background)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
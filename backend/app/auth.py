"""Password hashing, JWT tokens, and the 'who is calling?' dependencies."""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import Membership, User

load_dotenv()

ENV = os.getenv("ENV", "development")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key-do-not-use-in-production-0000")
if ENV == "production" and SECRET_KEY == "dev-only-insecure-key-do-not-use-in-production-0000":
    raise RuntimeError("Set a real SECRET_KEY in production")
ALGORITHM = "HS256"
TOKEN_HOURS = 24

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if creds is None:
        raise unauthorized
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    if user is None:
        raise unauthorized
    return user


def require_member(db: Session, user: User, room_id: int) -> Membership:
    """Use in EVERY room endpoint: 403 unless the user belongs to the room."""
    m = (
        db.query(Membership)
        .filter(Membership.user_id == user.id, Membership.room_id == room_id)
        .first()
    )
    if m is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this room")
    return m


def require_admin(db: Session, user: User, room_id: int) -> Membership:
    m = require_member(db, user, room_id)
    if m.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return m

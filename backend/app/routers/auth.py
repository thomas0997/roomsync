from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import create_token, get_current_user, hash_password, verify_password
from ..db import get_db
from ..models import User
from ..ratelimit import hit, limit_by_ip
from ..schemas import LoginIn, SignupIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_by_ip("signup", 5, 3600))],  # 5 signups per hour per address
)
def signup(data: SignupIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email, name=data.name.strip(), password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_token(user.id), user=user)


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
    return TokenOut(access_token=create_token(user.id), user=user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
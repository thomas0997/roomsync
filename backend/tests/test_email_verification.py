"""Email verification: POST /auth/verify, POST /auth/resend-verification, and that signup
sends the first link automatically."""
from datetime import datetime, timedelta, timezone

import pytest

from app import mailer, ratelimit
from app.db import SessionLocal
from app.models import EmailVerification, User
from tests.conftest import signup

SENT = []


@pytest.fixture(autouse=True)
def capture_mail(monkeypatch):
    SENT.clear()
    monkeypatch.setattr(mailer, "deliver", lambda **kw: SENT.append(kw) or True)


def token_from(mail):
    return mail["text"].split("#token=")[1].split()[0]


def test_signup_sends_a_verification_email_and_account_starts_unverified(client):
    headers = signup(client)
    assert len(SENT) == 1 and SENT[0]["to"] == "a@example.com" and SENT[0]["kind"] == "email_verification"
    me = client.get("/auth/me", headers=headers)
    assert me.json()["email_verified"] is False


def test_verify_with_the_link_marks_the_account_verified(client):
    headers = signup(client)
    token = token_from(SENT[0])
    r = client.post("/auth/verify", json={"token": token})
    assert r.status_code == 204
    me = client.get("/auth/me", headers=headers)
    assert me.json()["email_verified"] is True


def test_verify_link_is_in_the_fragment_and_only_the_hash_is_stored(client, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://roomsync.me")
    signup(client)
    assert "https://roomsync.me/pages/verify.html#token=" in SENT[0]["text"]
    token = token_from(SENT[0])
    with SessionLocal() as db:
        row = db.query(EmailVerification).one()
        assert token not in row.token_hash and len(row.token_hash) == 64


def test_verify_token_only_works_once(client):
    signup(client)
    token = token_from(SENT[0])
    assert client.post("/auth/verify", json={"token": token}).status_code == 204
    again = client.post("/auth/verify", json={"token": token})
    assert again.status_code == 400 and again.json()["detail"] == "Invalid or expired link"


def test_bad_and_expired_tokens_get_the_same_400(client):
    signup(client)
    token = token_from(SENT[0])
    bad = client.post("/auth/verify", json={"token": "nope"})
    assert bad.status_code == 400 and bad.json()["detail"] == "Invalid or expired link"
    with SessionLocal() as db:
        db.query(EmailVerification).update({"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
        db.commit()
    expired = client.post("/auth/verify", json={"token": token})
    assert expired.status_code == 400 and expired.json()["detail"] == "Invalid or expired link"


def test_deleted_account_cannot_be_verified(client):
    signup(client)
    token = token_from(SENT[0])
    with SessionLocal() as db:
        db.query(User).update({"deleted_at": datetime.now(timezone.utc)})
        db.commit()
    r = client.post("/auth/verify", json={"token": token})
    assert r.status_code == 400 and r.json()["detail"] == "Invalid or expired link"


def test_resend_requires_login(client):
    assert client.post("/auth/resend-verification").status_code == 401


def test_resend_sends_a_fresh_link_that_replaces_the_old_one(client):
    headers = signup(client)
    first = token_from(SENT[0])
    r = client.post("/auth/resend-verification", headers=headers)
    assert r.status_code == 204
    assert len(SENT) == 2 and SENT[1]["kind"] == "email_verification"
    second = token_from(SENT[1])
    assert first != second
    assert client.post("/auth/verify", json={"token": first}).status_code == 400  # replaced, no longer valid
    assert client.post("/auth/verify", json={"token": second}).status_code == 204


def test_resend_is_a_silent_no_op_once_already_verified(client):
    headers = signup(client)
    token = token_from(SENT[0])
    client.post("/auth/verify", json={"token": token})
    SENT.clear()
    r = client.post("/auth/resend-verification", headers=headers)
    assert r.status_code == 204
    assert SENT == []  # no second email once verified


def test_resend_is_rate_limited_per_account(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    headers = signup(client)
    codes = [client.post("/auth/resend-verification", headers=headers).status_code for _ in range(4)]
    assert codes == [204, 204, 204, 429]
    ratelimit.reset()


def test_verify_is_rate_limited_per_address(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    signup(client)
    codes = [client.post("/auth/verify", json={"token": "nope"}).status_code for _ in range(11)]
    assert codes[:10] == [400] * 10 and codes[10] == 429
    ratelimit.reset()

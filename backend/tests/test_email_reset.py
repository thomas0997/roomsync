"""Email sending, Contact/Feedback forwarding, and the forgot/reset password flow."""
from datetime import datetime, timedelta, timezone

import pytest

from app import mailer, ratelimit
from app.db import SessionLocal
from app.models import PasswordReset, User
from tests.conftest import signup

SENT = []


@pytest.fixture(autouse=True)
def capture_mail(monkeypatch):
    SENT.clear()
    monkeypatch.setattr(mailer, "deliver", lambda **kw: SENT.append(kw) or True)


def token_from(mail):
    return mail["text"].split("#token=")[1].split()[0]


def ask_reset(client, email="a@example.com"):
    return client.post("/auth/forgot", json={"email": email})


def test_forgot_known_and_unknown_email_look_identical(client):
    signup(client)
    known = ask_reset(client)
    unknown = ask_reset(client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 204
    assert known.content == unknown.content == b""
    assert len(SENT) == 1 and SENT[0]["to"] == "a@example.com" and SENT[0]["kind"] == "password_reset"


def test_reset_link_is_in_the_fragment_and_only_the_hash_is_stored(client, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://roomsync.me")
    signup(client)
    ask_reset(client)
    token = token_from(SENT[0])
    assert "https://roomsync.me/pages/reset.html#token=" in SENT[0]["text"]
    with SessionLocal() as db:
        row = db.query(PasswordReset).one()
        assert token not in row.token_hash and len(row.token_hash) == 64


def test_reset_changes_password_once_and_logs_everyone_out(client):
    old = signup(client)
    ask_reset(client)
    token = token_from(SENT[0])
    r = client.post("/auth/reset", json={"token": token, "new_password": "brandnew123"})
    assert r.status_code == 204
    assert client.get("/auth/me", headers=old).status_code == 401  # the old login is dead
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).status_code == 401
    login = client.post("/auth/login", json={"email": "a@example.com", "password": "brandnew123"})
    assert login.status_code == 200
    new = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/auth/me", headers=new).status_code == 200
    assert SENT[-1]["kind"] == "password_changed"
    again = client.post("/auth/reset", json={"token": token, "new_password": "another12345"})
    assert again.status_code == 400 and again.json()["detail"] == "Invalid or expired link"


def test_bad_and_expired_tokens_get_the_same_400(client):
    signup(client)
    ask_reset(client)
    token = token_from(SENT[0])
    bad = client.post("/auth/reset", json={"token": "nope", "new_password": "brandnew123"})
    assert bad.status_code == 400 and bad.json()["detail"] == "Invalid or expired link"
    with SessionLocal() as db:
        db.query(PasswordReset).update({"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
        db.commit()
    old = client.post("/auth/reset", json={"token": token, "new_password": "brandnew123"})
    assert old.status_code == 400 and old.json()["detail"] == "Invalid or expired link"
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).status_code == 200


def test_new_request_replaces_the_old_link(client):
    signup(client)
    ask_reset(client)
    first = token_from(SENT[0])
    ask_reset(client)
    second = token_from(SENT[1])
    assert client.post("/auth/reset", json={"token": first, "new_password": "brandnew123"}).status_code == 400
    assert client.post("/auth/reset", json={"token": second, "new_password": "brandnew123"}).status_code == 204


def test_short_or_too_long_new_password_is_422(client):
    signup(client)
    ask_reset(client)
    token = token_from(SENT[0])
    assert client.post("/auth/reset", json={"token": token, "new_password": "short"}).status_code == 422
    assert client.post("/auth/reset", json={"token": token, "new_password": "é" * 40}).status_code == 422


def test_deleted_account_gets_no_email(client):
    signup(client)
    with SessionLocal() as db:
        db.query(User).update({"deleted_at": datetime.now(timezone.utc)})
        db.commit()
    assert ask_reset(client).status_code == 204
    assert SENT == []


def test_forgot_is_rate_limited_per_email(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    signup(client)
    codes = [ask_reset(client).status_code for _ in range(4)]
    assert codes == [204, 204, 204, 429]
    ratelimit.reset()


def test_contact_and_feedback_are_forwarded_when_configured(client, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("CONTACT_INBOX", "thomas@roomsync.me")
    r = client.post("/contact", json={"name": "Sam\nBcc: x@y.z", "email": "sam@example.com", "message": "hello <b>team</b>"})
    assert r.status_code == 204
    mail = SENT[-1]
    assert mail["to"] == "thomas@roomsync.me" and mail["reply_to"] == "sam@example.com" and mail["kind"] == "contact"
    assert "\n" not in mail["subject"] and "hello <b>team</b>" in mail["text"]
    client.post("/feedback", json={"name": "Sam", "rating": 4, "message": "nice"})
    assert SENT[-1]["kind"] == "feedback" and "4/5" in SENT[-1]["subject"]


def test_honeypot_is_not_forwarded_and_nothing_sends_without_a_key(client, monkeypatch):
    monkeypatch.setenv("CONTACT_INBOX", "thomas@roomsync.me")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    client.post("/contact", json={"name": "Bot", "email": "b@example.com", "message": "x", "website": "spam"})
    assert SENT == []
    monkeypatch.delenv("RESEND_API_KEY")
    client.post("/contact", json={"name": "Sam", "email": "s@example.com", "message": "hi"})
    assert SENT == []


def test_deliver_never_raises_and_is_silent_without_a_key(monkeypatch):
    monkeypatch.undo()
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert mailer.deliver(to="a@b.co", subject="s", text="t", kind="x") is False
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert mailer.deliver(to="a@b.co", subject="s", text="t", kind="x") is False

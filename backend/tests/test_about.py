"""About page: Feedback and Contact forms (public, rate-limited, bot trap)."""
import pytest

from app import ratelimit
from app.db import SessionLocal
from app.models import ContactMessage, Feedback

GOOD_FEEDBACK = {"name": "Tony", "room": "The Bozos", "rating": 4, "message": "Love the calendar."}
GOOD_CONTACT = {"name": "Tony", "email": "tony@example.com", "message": "Can you add dark mode?"}


def _count(model):
    with SessionLocal() as db:
        return db.query(model).count()


def test_feedback_is_saved_without_logging_in(client):
    r = client.post("/feedback", json=GOOD_FEEDBACK)
    assert r.status_code == 204
    with SessionLocal() as db:
        row = db.query(Feedback).one()
        assert (row.name, row.room, row.rating, row.message) == ("Tony", "The Bozos", 4, "Love the calendar.")


def test_feedback_room_is_optional(client):
    body = {k: v for k, v in GOOD_FEEDBACK.items() if k != "room"}
    assert client.post("/feedback", json=body).status_code == 204
    with SessionLocal() as db:
        assert db.query(Feedback).one().room is None


def test_contact_is_saved_without_logging_in(client):
    assert client.post("/contact", json=GOOD_CONTACT).status_code == 204
    with SessionLocal() as db:
        row = db.query(ContactMessage).one()
        assert (row.name, row.email, row.message) == ("Tony", "tony@example.com", "Can you add dark mode?")


def test_text_is_trimmed(client):
    client.post("/feedback", json={**GOOD_FEEDBACK, "name": "  Tony  ", "message": "  hi  "})
    with SessionLocal() as db:
        row = db.query(Feedback).one()
        assert (row.name, row.message) == ("Tony", "hi")


def test_filled_trap_field_saves_nothing_but_looks_like_success(client):
    assert client.post("/feedback", json={**GOOD_FEEDBACK, "website": "http://spam.example"}).status_code == 204
    assert client.post("/contact", json={**GOOD_CONTACT, "website": "http://spam.example"}).status_code == 204
    assert _count(Feedback) == 0
    assert _count(ContactMessage) == 0


@pytest.mark.parametrize("change", [
    {"rating": 0}, {"rating": 6}, {"rating": "five"}, {"rating": None},
    {"message": ""}, {"message": "   "}, {"message": "x" * 2001},
    {"name": ""}, {"name": "x" * 101}, {"room": "x" * 101},
    {"surprise": "extra fields are refused"},
])
def test_bad_feedback_is_422(client, change):
    assert client.post("/feedback", json={**GOOD_FEEDBACK, **change}).status_code == 422
    assert _count(Feedback) == 0


@pytest.mark.parametrize("change", [
    {"email": "not-an-email"}, {"email": ""},
    {"message": ""}, {"message": "x" * 2001},
    {"name": ""}, {"surprise": 1},
])
def test_bad_contact_is_422(client, change):
    assert client.post("/contact", json={**GOOD_CONTACT, **change}).status_code == 422
    assert _count(ContactMessage) == 0


def test_missing_fields_are_422(client):
    assert client.post("/feedback", json={}).status_code == 422
    assert client.post("/contact", json={}).status_code == 422


def test_message_of_exactly_2000_characters_is_fine(client):
    assert client.post("/contact", json={**GOOD_CONTACT, "message": "x" * 2000}).status_code == 204


def test_both_forms_are_limited_to_5_per_hour_per_address(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    try:
        for _ in range(5):
            assert client.post("/feedback", json=GOOD_FEEDBACK).status_code == 204
        r = client.post("/feedback", json=GOOD_FEEDBACK)
        assert r.status_code == 429
        assert int(r.headers["Retry-After"]) >= 1
        for _ in range(5):
            assert client.post("/contact", json=GOOD_CONTACT).status_code == 204  # its own count
        assert client.post("/contact", json=GOOD_CONTACT).status_code == 429
    finally:
        ratelimit.reset()

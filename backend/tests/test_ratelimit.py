import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import ratelimit
from app.ratelimit import limit_by_user

from .conftest import signup


@pytest.fixture(autouse=True)
def limiter_on(monkeypatch):
    monkeypatch.setattr(ratelimit, "ENABLED", True)
    ratelimit.reset()
    yield
    ratelimit.reset()


def bad_login(client, email, ip="1.1.1.1"):
    return client.post(
        "/auth/login",
        json={"email": email, "password": "wrongpass1"},
        headers={"X-Forwarded-For": ip},
    )


def test_login_limited_per_address(client):
    for i in range(10):
        assert bad_login(client, f"user{i}@example.com").status_code == 401
    r = bad_login(client, "another@example.com")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    # a different address is not affected
    assert bad_login(client, "another@example.com", ip="2.2.2.2").status_code == 401


def test_login_limited_per_account_even_from_many_addresses(client):
    for i in range(10):
        assert bad_login(client, "victim@example.com", ip=f"9.9.9.{i}").status_code == 401
    assert bad_login(client, "victim@example.com", ip="9.9.9.200").status_code == 429


def test_signup_limited_per_address(client):
    for i in range(5):
        r = client.post("/auth/signup", json={"email": f"s{i}@example.com", "name": "S", "password": "password123"})
        assert r.status_code == 201
    r = client.post("/auth/signup", json={"email": "s5@example.com", "name": "S", "password": "password123"})
    assert r.status_code == 429


def test_forged_left_side_of_forwarded_header_is_ignored(client):
    # the caller invents a different first address each time; the real (last) address stays the same
    for i in range(10):
        r = client.post(
            "/auth/login",
            json={"email": f"f{i}@example.com", "password": "wrongpass1"},
            headers={"X-Forwarded-For": f"6.6.6.{i}, 5.5.5.5"},
        )
        assert r.status_code == 401
    r = client.post(
        "/auth/login",
        json={"email": "f99@example.com", "password": "wrongpass1"},
        headers={"X-Forwarded-For": "6.6.6.99, 5.5.5.5"},
    )
    assert r.status_code == 429


def test_window_expires(client, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now[0])
    for i in range(10):
        bad_login(client, f"w{i}@example.com")
    assert bad_login(client, "w10@example.com").status_code == 429
    now[0] += 61  # a minute later
    assert bad_login(client, "w11@example.com").status_code == 401


def test_limit_by_user_is_per_user_and_needs_login(client):
    alice = signup(client, "al@example.com", "Alice")
    bob = signup(client, "bo@example.com", "Bob")
    mini = FastAPI()

    @mini.post("/ping", dependencies=[Depends(limit_by_user("ping", 2, 60))])
    def ping():
        return {"ok": True}

    c = TestClient(mini)
    assert c.post("/ping").status_code == 401
    assert c.post("/ping", headers=alice).status_code == 200
    assert c.post("/ping", headers=alice).status_code == 200
    assert c.post("/ping", headers=alice).status_code == 429
    assert c.post("/ping", headers=bob).status_code == 200  # Bob has his own count
import os
import tempfile

# Must be set BEFORE the app is imported so tests use a throwaway database
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256-0000"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def signup(client, email="a@example.com", name="Alice", password="password123"):
    r = client.post("/auth/signup", json={"email": email, "name": name, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
def make_room(client, headers, name="CYB201"):
    r = client.post("/rooms", json={"name": name}, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def join_room(client, headers, invite_code):
    r = client.post("/rooms/join", json={"invite_code": invite_code}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()
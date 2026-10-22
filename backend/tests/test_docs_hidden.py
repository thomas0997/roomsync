from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import docs_settings


def test_docs_and_api_map_are_off_in_production():
    c = TestClient(FastAPI(**docs_settings("production")))
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404, path


def test_docs_stay_on_in_development():
    c = TestClient(FastAPI(**docs_settings("development")))
    assert c.get("/openapi.json").status_code == 200
    assert c.get("/docs").status_code == 200

from .conftest import signup


def test_requires_login(client):
    assert client.get("/users/me/settings").status_code == 401
    assert client.put("/users/me/settings", json={"show_empty_days": True}).status_code == 401


def test_defaults(client):
    h = signup(client)
    r = client.get("/users/me/settings", headers=h)
    assert r.status_code == 200
    assert r.json() == {
        "theme": "system", "show_empty_days": False, "notify_deadline_reminders": True,
        "notify_mentions": True, "notify_approvals": False, "timezone": "Asia/Manila", "task_colors": {},
    }


def test_partial_update_and_persists(client):
    h = signup(client)
    r = client.put("/users/me/settings", json={"show_empty_days": True}, headers=h)
    assert r.status_code == 200
    assert r.json()["show_empty_days"] is True
    assert r.json()["theme"] == "system"  # untouched fields keep their value
    assert client.get("/users/me/settings", headers=h).json()["show_empty_days"] is True


def test_task_colors(client):
    h = signup(client)
    r = client.put("/users/me/settings", json={"task_colors": {"exam": "#112233"}}, headers=h)
    assert r.status_code == 200
    assert r.json()["task_colors"] == {"exam": "#112233"}
    # a second call merges, it does not replace
    r = client.put("/users/me/settings", json={"task_colors": {"quiz": "#445566"}}, headers=h)
    assert r.json()["task_colors"] == {"exam": "#112233", "quiz": "#445566"}


def test_task_colors_validation(client):
    h = signup(client)
    assert client.put("/users/me/settings", json={"task_colors": {"homework": "#112233"}}, headers=h).status_code == 422
    assert client.put("/users/me/settings", json={"task_colors": {"exam": "red"}}, headers=h).status_code == 422


def test_rejects_unknown_fields_and_empty_body(client):
    h = signup(client)
    assert client.put("/users/me/settings", json={}, headers=h).status_code == 422
    assert client.put("/users/me/settings", json={"nope": 1}, headers=h).status_code == 422
    assert client.put("/users/me/settings", json={"theme": "neon"}, headers=h).status_code == 422

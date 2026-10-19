def test_root_redirects_to_landing_page(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/pages/index.html"


def test_frontend_files_are_served(client):
    assert client.get("/pages/login.html").status_code == 200
    assert client.get("/css/styles.css").status_code == 200
    assert client.get("/js/rooms.js").status_code == 200
    assert client.get("/assets/roomsync_logo.png").status_code == 200


def test_backend_and_secrets_are_not_served(client):
    for path in ("/backend/app/db.py", "/backend/.env", "/.env", "/pages/../backend/app/db.py", "/pages/%2e%2e/backend/app/db.py", "/CLAUDE.md"):
        assert client.get(path).status_code == 404, path


def test_api_still_works(client):
    assert client.get("/health").json() == {"status": "ok"}
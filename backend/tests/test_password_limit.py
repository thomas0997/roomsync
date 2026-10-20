from .conftest import signup


def test_72_byte_password_works(client):
    pw = "a" * 72
    signup(client, "p72@example.com", "P", pw)
    r = client.post("/auth/login", json={"email": "p72@example.com", "password": pw})
    assert r.status_code == 200


def test_73_byte_password_is_422_not_500(client):
    r = client.post("/auth/signup", json={"email": "p73@example.com", "name": "P", "password": "a" * 73})
    assert r.status_code == 422


def test_emoji_password_counts_bytes(client):
    # 19 emoji = 76 bytes (4 bytes each), only 19 characters
    r = client.post("/auth/signup", json={"email": "emo@example.com", "name": "P", "password": "😀" * 19})
    assert r.status_code == 422


def test_long_login_password_is_401_not_500(client):
    signup(client, "ok@example.com", "P")
    r = client.post("/auth/login", json={"email": "ok@example.com", "password": "a" * 100})
    assert r.status_code == 401
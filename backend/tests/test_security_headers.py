"""Security headers: CSP (blocks injected scripts), nosniff, clickjacking, HSTS over HTTPS, no caching of API answers."""
from .conftest import signup


def test_headers_on_frontend_pages(client):
    r = client.get("/pages/home.html")
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]  # scripts may NOT be inline
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert r.headers["cache-control"] == "no-cache"


def test_headers_on_api_answers(client):
    h = signup(client)
    r = client.get("/users/me", headers=h)
    assert r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"  # personal data is never cached


def test_hsts_only_over_https(client):
    assert "strict-transport-security" not in client.get("/health").headers
    r = client.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert r.headers["strict-transport-security"].startswith("max-age=")


def test_api_docs_are_exempt_from_csp(client):
    r = client.get("/docs")
    assert r.status_code == 200
    assert "content-security-policy" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"


def test_no_inline_scripts_left_in_pages():
    """The CSP forbids inline scripts, so none of our pages may contain one."""
    import re
    from pathlib import Path

    pages = Path(__file__).resolve().parents[2] / "pages"
    for page in pages.glob("*.html"):
        for tag in re.findall(r"<script\b[^>]*>", page.read_text()):
            assert "src=" in tag, f"inline <script> in {page.name}"
        assert not re.search(r"\son[a-z]+=\"", page.read_text()), f"inline event handler in {page.name}"
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .routers import about, approvals, auth, avatar, discussion, notes, profile, rooms, task_state, tasks

load_dotenv()



def docs_settings(env: str) -> dict:
    """In production the interactive docs and the API map (openapi.json) are switched off,
    so strangers cannot read how the API works. Locally (ENV not 'production') they stay on."""
    if env == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


app = FastAPI(title="RoomSync API", **docs_settings(os.getenv("ENV", "development")))

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5500").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # we use Bearer tokens, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Make browsers re-check our frontend files on every load. The server already
# sends an ETag, so an unchanged file costs a tiny "304 Not Modified" reply, and a
# changed file (after a deploy) is picked up straight away instead of staying stale.
STATIC_PREFIXES = ("/pages/", "/css/", "/js/", "/assets/")

# Content Security Policy: the browser only runs OUR scripts, so injected code (XSS) is blocked.
# Styles may be inline (the pages use style="..."); fonts come from Google Fonts; images from us
# plus data: (small SVGs inside the CSS) and blob: (profile photos the page downloads with the login token). The API is on the same address, so connect-src is 'self'.
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
# The built-in API docs load their page from a CDN, so they are exempt from the CSP above.
NO_CSP_PATHS = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not path.startswith(NO_CSP_PATHS):
        h["Content-Security-Policy"] = CSP
    if request.headers.get("x-forwarded-proto") == "https":
        h["Strict-Transport-Security"] = "max-age=31536000"  # the browser will only use HTTPS for a year
    if path.startswith(STATIC_PREFIXES):
        h["Cache-Control"] = "no-cache"
    elif not path.startswith(NO_CSP_PATHS) and path != "/health":
        h["Cache-Control"] = "no-store"  # API answers hold personal data: never cache them
    return response


# Tables are created and changed by Alembic migrations, not by the app: run `alembic upgrade head`.

for module in (auth, rooms, tasks, task_state, approvals, notes, discussion, profile, avatar, about):
    app.include_router(module.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the frontend from the same address as the API (no CORS needed).
# Only these four folders are public; backend/, .env and the rest of the repo are not.
REPO_ROOT = Path(__file__).resolve().parents[2]
for folder in ("pages", "css", "js", "assets"):
    app.mount(f"/{folder}", StaticFiles(directory=REPO_ROOT / folder), name=folder)


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/pages/index.html")
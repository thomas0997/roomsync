import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .routers import approvals, auth, discussion, notes, profile, rooms, tasks

load_dotenv()

app = FastAPI(title="RoomSync API")

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5500").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # we use Bearer tokens, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tables are created and changed by Alembic migrations, not by the app: run `alembic upgrade head`.

for module in (auth, rooms, tasks, approvals, notes, discussion, profile):
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
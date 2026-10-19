# RoomSync: project rules for any AI assistant

RoomSync is a student capstone web app (HAU, CYB-201): classmates share deadlines in "rooms". A task must be approved by a room admin before it appears on the room's weekly board and calendar. This is a REAL product shipping Nov 7, not a demo.

## Stack (fixed, do not suggest alternatives)
- Frontend: plain HTML/CSS/JS in `pages/`, `css/`, `js/` (no framework). Design is DONE.
- Backend: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, bcrypt, PyJWT, pytest.
- DB: SQLite locally (`DATABASE_URL=sqlite:///./roomsync.db`), Neon Postgres in production.
- Hosting: ONE Render web service serves the API and the frontend on roomsync.me (no CORS). Render auto-deploys from `feat/backend-skeleton`, so anything merged there goes LIVE. Vercel only serves the static `main` branch (demo for grading).

## Source of truth
- `docs/api-contract.md` v2: endpoints, JSON shapes, tiers (T1 = Nov 7 core, T2 = Nov to Dec, T3 = after launch). Build ONLY T1 unless Thomas says otherwise.
- `docs/feature-spec.md`: page-by-page behavior.

## Team and ownership (two people, beginners at backend)
- Thomas: models.py, auth, rooms, /users/me, deploy, and the login/register/home/settings/profile pages.
- Daniel: tasks, approvals, discussion (`routers/` files of the same names) and the calendar/approve/discussion pages.
- Only edit your own router files. Shared files (`models.py`, `main.py`, `db.py`, `schemas.py`, `conftest.py`, `requirements.txt`): small edits only, pull first, tell your partner BEFORE changing. After every push your partner runs `git pull --rebase`.

## Rules
1. The contract is law. Do not invent or rename endpoints. To change one, edit the contract FIRST and tell your partner.
2. Every room endpoint MUST call `require_member(db, user, room_id)` (or `require_admin`) from `app/auth.py` before touching data. Never trust a room_id, task_id or user_id from the client without checking membership.
3. Validate input with Pydantic schemas. Use the SQLAlchemy ORM, never build SQL from strings.
4. Never hardcode secrets. They live in `backend/.env` (gitignored). Update `.env.example` when adding a variable. Never paste secrets, tokens or the database URL into chat or git.
5. Every new endpoint gets a pytest covering the happy path AND the failure cases (non-member 403, no token 401, bad input 422). Use the helpers in `tests/conftest.py` (`client`, `signup`, `make_room`, `join_room`). Run all tests before every commit. Only merge code that passes.
6. Frontend: replace hardcoded data with `fetch()` calls. Keep the existing look and class names. JWT in `localStorage` under `roomsync_token`, sent as `Authorization: Bearer <token>`. API base URL in one place: `js/config.js` (`window.ROOMSYNC.API_BASE`).
7. Frontend security: render ALL user-supplied text with `textContent`, never `innerHTML`. No hardcoded logins.
8. Never log message content. Room chat is not end-to-end encrypted; do not claim it is.
9. Small tasks, one endpoint at a time. Explain code in plain words (we present it).
10. Never point a local `.env` at the Neon (production) database. Local work uses SQLite only.

## Git (IMPORTANT)
- `main` is frontend-only until the professor finishes grading. NEVER merge backend work into `main`, and never push to `main`. `main` keeps the demo login (admin/admin).
- Work on a branch off `feat/backend-skeleton` (e.g. `feat/tasks`). Pull requests go into `feat/backend-skeleton`.
- Never run `git add .` from the repo root; add files by name.
- Name new files in lowercase (Vercel/Linux is case-sensitive).

## Database changes (Alembic)
- Any change to `backend/app/models.py` needs an Alembic migration in the SAME commit.
- Steps (from `backend/`): `alembic revision --autogenerate -m "short description"`, read the generated file in `alembic/versions/`, then `alembic upgrade head`. Commit models.py and the migration together.
- Never edit a migration that is already pushed. Make a new one.
- The app does NOT create tables itself. A fresh local DB needs `alembic upgrade head`.
- Tests build their own temporary DB and do not need Alembic.

## Commands (from `backend/`)
- Setup (Mac/Linux): `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && alembic upgrade head`
- Setup (Windows PowerShell): `python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements.txt; alembic upgrade head`
- Run: `uvicorn app.main:app --reload`, then open http://localhost:8000/docs
- Test: `python -m pytest -q` (34+ must pass)
# RoomSync: project rules for any AI assistant

RoomSync is a student capstone web app (HAU, CYB-201): classmates share deadlines in "rooms". A task must be
approved by peers before it appears on the room's weekly board and calendar.

## Stack (fixed, do not suggest alternatives)
- Frontend: plain HTML/CSS/JS in `pages/`, `css/`, `js/` (no framework). Deployed on Vercel. Design is DONE.
- Backend: Python 3.12+, FastAPI, SQLAlchemy 2, bcrypt, PyJWT, pytest. Deployed on Render.
- DB: SQLite locally (`DATABASE_URL=sqlite:///./roomsync.db`), Neon Postgres in production.

## Team and ownership (two people, beginners at backend)
- Thomas: setup, models for users/rooms, auth, rooms, deploy, login/home/settings pages.
- Friend: tasks, approvals, notes, discussion, profile (`routers/` files of the same names) and their pages.
- Only edit your own router files. For shared files (`models.py`, `main.py`, `schemas.py`) keep edits small, pull first, tell your partner.

## Rules
1. `docs/api-contract.md` is the source of truth for endpoints and JSON shapes. Do not invent or rename endpoints. If you must change one, edit the contract first and tell the partner.
2. Every room endpoint MUST call `require_member(db, user, room_id)` (or `require_admin`) from `app/auth.py` before touching data. Never trust a room_id or task_id from the client without checking membership.
3. Validate input with Pydantic schemas. Use the SQLAlchemy ORM, never build SQL from strings.
4. Never hardcode secrets. They live in `backend/.env` (gitignored). Update `.env.example` when adding a variable.
5. Every new endpoint gets a pytest in `backend/tests/` covering the happy path AND a permission failure (non-member gets 403, no token gets 401).
6. Frontend: replace hardcoded data/localStorage with `fetch()` calls. Keep the existing look and class names; do not restyle. Store the JWT in `localStorage` under `roomsync.token`, send `Authorization: Bearer <token>`. API base URL goes in one place (`js/config.js`).
7. Small tasks. Explain code in plain words (we must explain it in our presentation). Run the tests before every commit.

## Commands (from `backend/`)
- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (Windows: `.venv\Scripts\activate`)
- Run: `uvicorn app.main:app --reload`  then open http://localhost:8000/docs
- Test: `python -m pytest -q`

## Git
Branch per feature (`feat/tasks`), pull request into `main`, never push to `main` directly, commit small and often.

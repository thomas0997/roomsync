"""Rate limiting: "at most N tries per time window, then 429 Too Many Requests".

How to use it on an endpoint (one line):

    from ..ratelimit import limit_by_user          # needs a logged-in user
    @router.post("/rooms/{room_id}/tasks", dependencies=[Depends(limit_by_user("create_task", 20, 3600))])

    from ..ratelimit import limit_by_ip            # for public endpoints (login, signup)
    @router.post("/signup", dependencies=[Depends(limit_by_ip("signup", 5, 3600))])

Counts live in this server's memory: fine for one Render instance. They reset when the server
restarts or redeploys. With several instances we would move the counts to Redis.
"""
import os
import threading
import time
from collections import deque

from fastapi import Depends, HTTPException, Request

from .auth import get_current_user
from .models import User

# Tests switch this off (see tests/conftest.py) and switch it on in tests/test_ratelimit.py.
ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false"
# How many proxy servers sit between the internet and the app. Render adds the caller's address
# to the END of X-Forwarded-For, so we read it from the right (the left side can be faked).
TRUSTED_PROXY_HOPS = max(1, int(os.getenv("TRUSTED_PROXY_HOPS", "1")))

_MAX_KEYS = 50_000
_hits: dict[str, tuple[int, deque]] = {}  # key -> (window_seconds, timestamps)
_lock = threading.Lock()  # endpoints run in several threads at once


def reset() -> None:
    """Forget all counts (used by tests)."""
    with _lock:
        _hits.clear()


def hit(name: str, key: str, limit: int, window_seconds: int) -> None:
    """Count one try for (name, key). Raises 429 when the limit inside the window is used up."""
    if not ENABLED:
        return
    now = time.monotonic()
    full_key = f"{name}:{key}"
    with _lock:
        if len(_hits) > _MAX_KEYS:  # housekeeping so memory can't grow forever
            for k in [k for k, (w, q) in _hits.items() if not q or q[-1] <= now - w]:
                del _hits[k]
        _, times = _hits.setdefault(full_key, (window_seconds, deque()))
        while times and times[0] <= now - window_seconds:
            times.popleft()
        if len(times) >= limit:
            retry = int(times[0] + window_seconds - now) + 1
            raise HTTPException(
                429,
                f"Too many requests. Try again in {retry} seconds.",
                headers={"Retry-After": str(retry)},
            )
        times.append(now)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    if parts:
        return parts[-TRUSTED_PROXY_HOPS] if len(parts) >= TRUSTED_PROXY_HOPS else parts[0]
    return request.client.host if request.client else "unknown"


def limit_by_ip(name: str, limit: int, window_seconds: int):
    """Dependency: limit per caller address. Use on public endpoints."""

    def dependency(request: Request) -> None:
        hit(name, f"ip:{client_ip(request)}", limit, window_seconds)

    return dependency


def limit_by_user(name: str, limit: int, window_seconds: int):
    """Dependency: limit per logged-in user. A missing or bad token still gives 401 first."""

    def dependency(user: User = Depends(get_current_user)) -> None:
        hit(name, f"user:{user.id}", limit, window_seconds)

    return dependency
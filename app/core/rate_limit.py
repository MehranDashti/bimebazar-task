"""Lightweight in-memory rate limiter — zero external dependencies.

Fixed-window-ish sliding limiter keyed by client IP + path. Intended as a sane
default for a single-process deployment. For multi-worker / multi-instance
production, swap the backing store for Redis (or use slowapi) — the public
`RateLimiter` dependency interface can stay the same.

Usage:
    from fastapi import Depends
    from app.core.rate_limit import RateLimiter

    login_limiter = RateLimiter(times=5, seconds=60)

    @router.post("/login", dependencies=[Depends(login_limiter)])
    async def login(...):
        ...
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.core.config import settings


class RateLimiter:
    def __init__(self, times: int, seconds: int) -> None:
        self.times = times
        self.seconds = seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def __call__(self, request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        client_host = request.client.host if request.client else "unknown"
        key = f"{client_host}:{request.url.path}"
        now = time.monotonic()
        window_start = now - self.seconds

        hits = [t for t in self._hits[key] if t > window_start]
        if len(hits) >= self.times:
            retry_after = int(self.seconds - (now - hits[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        self._hits[key] = hits

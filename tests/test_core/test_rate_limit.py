import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.rate_limit import RateLimiter


class _FakeRequest:
    """Minimal stand-in exposing the attributes RateLimiter reads."""

    class _Client:
        host = "203.0.113.7"

    class _Url:
        path = "/api/v1/auth/login"

    client = _Client()
    url = _Url()


async def test_rate_limiter_allows_under_limit():
    settings.RATE_LIMIT_ENABLED = True
    try:
        limiter = RateLimiter(times=3, seconds=60)
        for _ in range(3):
            await limiter(_FakeRequest())  # no raise
    finally:
        settings.RATE_LIMIT_ENABLED = False


async def test_rate_limiter_blocks_over_limit():
    settings.RATE_LIMIT_ENABLED = True
    try:
        limiter = RateLimiter(times=2, seconds=60)
        await limiter(_FakeRequest())
        await limiter(_FakeRequest())
        with pytest.raises(HTTPException) as exc_info:
            await limiter(_FakeRequest())
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
    finally:
        settings.RATE_LIMIT_ENABLED = False


async def test_rate_limiter_disabled_is_noop():
    settings.RATE_LIMIT_ENABLED = False
    limiter = RateLimiter(times=1, seconds=60)
    for _ in range(5):
        await limiter(_FakeRequest())  # never raises while disabled

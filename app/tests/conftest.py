import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all models with Base.metadata
from app.core.config import settings
from app.db.session import Base, get_db
from main import app

# The in-memory rate limiter keys on client IP; the test client is always
# 127.0.0.1, so leaving it on would throttle the suite. Exercised directly in
# app/tests/test_core/test_rate_limit.py instead.
settings.RATE_LIMIT_ENABLED = False

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    yield
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _make_auth_headers(client: AsyncClient, email: str, username: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "username": username,
            "full_name": "Test User",
            "password": "Password1",
        },
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password1"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    return await _make_auth_headers(client, "test@example.com", "testuser")


@pytest_asyncio.fixture
async def user_headers(client: AsyncClient) -> dict[str, str]:
    """Alias for auth_headers — used by auth route tests."""
    return await _make_auth_headers(client, "user@test.com", "testuser2")

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.core.dependencies import get_order_service
from app.core.exceptions import NotFoundError
from app.models.order import OrderStatus
from main import app

# ── Helpers ───────────────────────────────────────────────────────────────────

def _stub_order(order_id: int = 1, reservation_id: int = 1):
    return SimpleNamespace(
        id=order_id,
        reservation_id=reservation_id,
        user_id="user_test",
        status=OrderStatus.created,
        created_at=datetime.now(UTC),
    )


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def override_order_service():
    mock_svc = MagicMock()
    app.dependency_overrides[get_order_service] = lambda: mock_svc
    yield mock_svc
    app.dependency_overrides.pop(get_order_service, None)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_order_returns_200(client: AsyncClient, override_order_service):
    override_order_service.get_by_id = AsyncMock(return_value=_stub_order())

    resp = await client.get("/api/v1/orders/1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == 1
    assert data["reservation_id"] == 1
    assert data["status"] == OrderStatus.created.value


@pytest.mark.asyncio
async def test_get_order_returns_all_fields(client: AsyncClient, override_order_service):
    stub = _stub_order(order_id=7, reservation_id=3)
    override_order_service.get_by_id = AsyncMock(return_value=stub)

    resp = await client.get("/api/v1/orders/7")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == 7
    assert data["reservation_id"] == 3
    assert data["user_id"] == "user_test"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_get_order_not_found_returns_404(client: AsyncClient, override_order_service):
    override_order_service.get_by_id = AsyncMock(side_effect=NotFoundError("order not found"))

    resp = await client.get("/api/v1/orders/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_order_calls_service_with_order_id(client: AsyncClient, override_order_service):
    override_order_service.get_by_id = AsyncMock(return_value=_stub_order(order_id=12))

    await client.get("/api/v1/orders/12")

    override_order_service.get_by_id.assert_awaited_once_with(12)


@pytest.mark.asyncio
async def test_get_orders_without_id_returns_404(client: AsyncClient):
    resp = await client.get("/api/v1/orders")
    assert resp.status_code == 404

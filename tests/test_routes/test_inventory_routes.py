from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.core.dependencies import get_inventory_service
from app.core.exceptions import NotFoundError
from main import app


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def override_inventory_service():
    mock_svc = MagicMock()
    app.dependency_overrides[get_inventory_service] = lambda: mock_svc
    yield mock_svc
    app.dependency_overrides.pop(get_inventory_service, None)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_availability_returns_200(client: AsyncClient, override_inventory_service):
    override_inventory_service.get_availability = AsyncMock(return_value={
        "product_id": 1,
        "sources": [
            {
                "provider_id": 1,
                "provider_name": "InternalStock",
                "qty_available": 10,
                "qty_reserved": 2,
                "effective_available": 8,
                "last_synced_at": None,
            }
        ],
    })

    resp = await client.get("/api/v1/inventory/1/availability")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["product_id"] == 1
    assert len(data["sources"]) == 1
    assert data["sources"][0]["effective_available"] == 8


@pytest.mark.asyncio
async def test_get_availability_empty_sources(client: AsyncClient, override_inventory_service):
    override_inventory_service.get_availability = AsyncMock(return_value={
        "product_id": 5,
        "sources": [],
    })

    resp = await client.get("/api/v1/inventory/5/availability")
    assert resp.status_code == 200
    assert resp.json()["data"]["sources"] == []


@pytest.mark.asyncio
async def test_get_availability_calls_service_with_product_id(client: AsyncClient, override_inventory_service):
    override_inventory_service.get_availability = AsyncMock(return_value={"product_id": 7, "sources": []})

    await client.get("/api/v1/inventory/7/availability")

    override_inventory_service.get_availability.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_get_availability_service_raises_not_found_returns_404(client: AsyncClient, override_inventory_service):
    override_inventory_service.get_availability = AsyncMock(side_effect=NotFoundError("product not found"))

    resp = await client.get("/api/v1/inventory/999/availability")
    assert resp.status_code == 404

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
async def test_sync_provider_returns_200_with_counts(client: AsyncClient, override_inventory_service):
    override_inventory_service.sync_from_provider = AsyncMock(return_value={
        "updated": 5, "errors": [], "message": "",
    })

    resp = await client.post("/api/v1/providers/1/sync")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["updated"] == 5
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_sync_provider_partial_failure_records_errors(client: AsyncClient, override_inventory_service):
    override_inventory_service.sync_from_provider = AsyncMock(return_value={
        "updated": 2,
        "errors": ["SKU-001: connection refused"],
        "message": "",
    })

    resp = await client.post("/api/v1/providers/3/sync")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["updated"] == 2
    assert len(data["errors"]) == 1


@pytest.mark.asyncio
async def test_sync_provider_not_found_returns_404(client: AsyncClient, override_inventory_service):
    override_inventory_service.sync_from_provider = AsyncMock(side_effect=NotFoundError("provider not found"))

    resp = await client.post("/api/v1/providers/999/sync")
    assert resp.status_code == 404



@pytest.mark.asyncio
async def test_sync_provider_calls_service_with_provider_id(client: AsyncClient, override_inventory_service):
    override_inventory_service.sync_from_provider = AsyncMock(return_value={"updated": 0, "errors": [], "message": ""})

    await client.post("/api/v1/providers/42/sync")

    override_inventory_service.sync_from_provider.assert_awaited_once_with(42)

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import NotFoundError
from app.models.inventory_provider import ProviderType
from app.providers.base import ProviderError
from app.repositories.inventory_repository import InventoryRepository
from app.services.inventory_service import InventoryService

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_provider(pid: int = 1, ptype: ProviderType = ProviderType.external, active: bool = True):
    return SimpleNamespace(id=pid, name="TestProvider", type=ptype, is_active=active)


def _make_inventory_row(provider_id: int = 1, qty_available: int = 10, qty_reserved: int = 2):
    return SimpleNamespace(
        id=1, product_id=1, provider_id=provider_id,
        qty_available=qty_available, qty_reserved=qty_reserved,
        last_synced_at=None,
        provider=SimpleNamespace(name="TestProvider"),
        product=SimpleNamespace(sku="TEST-SKU"),
    )


def _build_service(rows=None, db_execute_result=None):
    inv_repo = AsyncMock(spec=InventoryRepository)
    inv_repo.db = AsyncMock()
    inv_repo.get_all_by_product = AsyncMock(return_value=rows or [])
    inv_repo.get_all_by_provider = AsyncMock(return_value=rows or [])
    inv_repo.db.flush = AsyncMock()
    if db_execute_result is not None:
        inv_repo.db.execute = AsyncMock(return_value=db_execute_result)
    return InventoryService(inv_repo=inv_repo), inv_repo


def _mock_execute(provider_obj):
    result = MagicMock()
    result.scalars.return_value.first.return_value = provider_obj
    return result


# ── get_availability ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_availability_no_inventory_returns_empty():
    svc, _ = _build_service(rows=[])
    data = await svc.get_availability(product_id=99)
    assert data["product_id"] == 99
    assert data["sources"] == []


@pytest.mark.asyncio
async def test_get_availability_single_provider():
    row = _make_inventory_row(qty_available=10, qty_reserved=3)
    svc, _ = _build_service(rows=[row])
    data = await svc.get_availability(product_id=1)
    assert len(data["sources"]) == 1
    src = data["sources"][0]
    assert src["qty_available"] == 10
    assert src["qty_reserved"] == 3
    assert src["effective_available"] == 7


@pytest.mark.asyncio
async def test_get_availability_multiple_providers():
    rows = [
        _make_inventory_row(provider_id=1, qty_available=5, qty_reserved=1),
        _make_inventory_row(provider_id=2, qty_available=20, qty_reserved=5),
    ]
    svc, _ = _build_service(rows=rows)
    data = await svc.get_availability(product_id=1)
    assert len(data["sources"]) == 2
    assert data["sources"][0]["effective_available"] == 4
    assert data["sources"][1]["effective_available"] == 15


@pytest.mark.asyncio
async def test_get_availability_fully_reserved_row():
    row = _make_inventory_row(qty_available=5, qty_reserved=5)
    svc, _ = _build_service(rows=[row])
    data = await svc.get_availability(product_id=1)
    assert data["sources"][0]["effective_available"] == 0


# ── sync_from_provider ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_from_provider_not_found_raises():
    svc, _ = _build_service(db_execute_result=_mock_execute(None))
    with pytest.raises(NotFoundError):
        await svc.sync_from_provider(provider_id=99)


@pytest.mark.asyncio
async def test_sync_from_provider_inactive_raises():
    provider = _make_provider(active=False)
    svc, _ = _build_service(db_execute_result=_mock_execute(provider))
    with pytest.raises(ValueError, match="inactive"):
        await svc.sync_from_provider(provider_id=1)


@pytest.mark.asyncio
async def test_sync_from_provider_internal_skips_sync():
    provider = _make_provider(ptype=ProviderType.internal)
    svc, _ = _build_service(db_execute_result=_mock_execute(provider))
    result = await svc.sync_from_provider(provider_id=1)
    assert result["updated"] == 0
    assert "internal" in result.get("message", "")


@pytest.mark.asyncio
async def test_sync_from_provider_success_updates_qty(monkeypatch):
    provider = _make_provider()
    row = _make_inventory_row()
    svc, inv_repo = _build_service(rows=[row], db_execute_result=_mock_execute(provider))

    mock_adapter = AsyncMock()
    mock_adapter.check_stock = AsyncMock(return_value=42)
    monkeypatch.setattr(
        "app.services.inventory_service.ProviderRegistry.resolve",
        lambda p: mock_adapter,
    )

    result = await svc.sync_from_provider(provider_id=1)
    assert result["updated"] == 1
    assert result["errors"] == []
    assert row.qty_available == 42
    assert row.last_synced_at is not None


@pytest.mark.asyncio
async def test_sync_from_provider_partial_failure_records_error(monkeypatch):
    provider = _make_provider()
    row = _make_inventory_row()
    svc, _ = _build_service(rows=[row], db_execute_result=_mock_execute(provider))

    mock_adapter = AsyncMock()
    mock_adapter.check_stock = AsyncMock(side_effect=ProviderError("connection refused"))
    monkeypatch.setattr(
        "app.services.inventory_service.ProviderRegistry.resolve",
        lambda p: mock_adapter,
    )

    result = await svc.sync_from_provider(provider_id=1)
    assert result["updated"] == 0
    assert len(result["errors"]) == 1
    assert "TEST-SKU" in result["errors"][0]


@pytest.mark.asyncio
async def test_sync_from_provider_no_rows_returns_zero(monkeypatch):
    provider = _make_provider()
    svc, _ = _build_service(rows=[], db_execute_result=_mock_execute(provider))
    result = await svc.sync_from_provider(provider_id=1)
    assert result["updated"] == 0
    assert result["errors"] == []

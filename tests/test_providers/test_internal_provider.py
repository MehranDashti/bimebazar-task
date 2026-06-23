from types import SimpleNamespace

import pytest

from app.providers.base import InsufficientProviderStock
from app.providers.internal import InternalProviderAdapter


def _make_inventory(qty_available: int, qty_reserved: int):
    return SimpleNamespace(
        qty_available=qty_available,
        qty_reserved=qty_reserved,
        product=SimpleNamespace(sku="TEST-SKU"),
    )


@pytest.mark.asyncio
async def test_check_stock_returns_effective():
    inv = _make_inventory(10, 3)
    adapter = InternalProviderAdapter(inv)
    assert await adapter.check_stock("TEST-SKU") == 7


@pytest.mark.asyncio
async def test_hold_stock_success_increments_reserved():
    inv = _make_inventory(10, 2)
    adapter = InternalProviderAdapter(inv)
    result = await adapter.hold_stock("TEST-SKU", 3, reservation_id=1)
    assert result is None
    assert inv.qty_reserved == 5


@pytest.mark.asyncio
async def test_hold_stock_insufficient_raises():
    inv = _make_inventory(5, 4)
    adapter = InternalProviderAdapter(inv)
    with pytest.raises(InsufficientProviderStock):
        await adapter.hold_stock("TEST-SKU", 2, reservation_id=1)
    assert inv.qty_reserved == 4  # unchanged


@pytest.mark.asyncio
async def test_hold_stock_exact_boundary_succeeds():
    inv = _make_inventory(5, 3)
    adapter = InternalProviderAdapter(inv)
    result = await adapter.hold_stock("TEST-SKU", 2, reservation_id=1)
    assert result is None
    assert inv.qty_reserved == 5


@pytest.mark.asyncio
async def test_release_hold_returns_true():
    inv = _make_inventory(10, 5)
    adapter = InternalProviderAdapter(inv)
    assert await adapter.release_hold("any-ref") is True


@pytest.mark.asyncio
async def test_confirm_hold_returns_true():
    inv = _make_inventory(10, 5)
    adapter = InternalProviderAdapter(inv)
    assert await adapter.confirm_hold("any-ref") is True

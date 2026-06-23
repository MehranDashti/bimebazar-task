from types import SimpleNamespace

import pytest

from app.models.inventory_provider import ProviderType
from app.providers.external_http import ExternalHttpProviderAdapter
from app.providers.internal import InternalProviderAdapter
from app.providers.registry import ProviderRegistry


def _provider(ptype: ProviderType):
    return SimpleNamespace(
        id=1, name="Test", type=ptype, is_active=True,
        base_url="http://warehouse.example.com",
        timeout_seconds=5,
        capabilities={},
        auth_config=None,
    )


def _inventory_row():
    return SimpleNamespace(
        id=1, product_id=1, qty_available=10, qty_reserved=2,
        product=SimpleNamespace(sku="SKU-001"),
    )


def test_resolve_internal_with_row_returns_internal_adapter():
    provider = _provider(ProviderType.internal)
    row = _inventory_row()
    adapter = ProviderRegistry.resolve(provider, inventory_row=row)
    assert isinstance(adapter, InternalProviderAdapter)


def test_resolve_external_returns_external_adapter():
    provider = _provider(ProviderType.external)
    adapter = ProviderRegistry.resolve(provider)
    assert isinstance(adapter, ExternalHttpProviderAdapter)


def test_resolve_internal_without_row_raises():
    provider = _provider(ProviderType.internal)
    with pytest.raises(ValueError, match="inventory_row"):
        ProviderRegistry.resolve(provider, inventory_row=None)


def test_resolve_internal_row_none_default_raises():
    provider = _provider(ProviderType.internal)
    with pytest.raises(ValueError):
        ProviderRegistry.resolve(provider)

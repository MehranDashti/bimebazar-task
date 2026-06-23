from types import SimpleNamespace

import httpx
import pytest
import respx

from app.models.inventory_provider import ProviderType
from app.providers.base import (
    CapabilityNotSupported,
    InsufficientProviderStock,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.external_http import ExternalHttpProviderAdapter


def _make_provider(capabilities: dict | None = None):
    return SimpleNamespace(
        name="TestProvider",
        type=ProviderType.external,
        base_url="http://fake-wh",
        timeout_seconds=5,
        capabilities=capabilities or {
            "check_stock": True,
            "hold_stock": True,
            "release_hold": True,
            "confirm_hold": True,
        },
        auth_config={"type": "api_key", "header": "X-Key", "value": "test-key"},
    )


@pytest.mark.asyncio
async def test_hold_stock_success():
    with respx.mock(base_url="http://fake-wh") as mock:
        mock.post("/holds").mock(
            return_value=httpx.Response(200, json={"hold_ref": "WH-123"})
        )
        adapter = ExternalHttpProviderAdapter(_make_provider())
        ref = await adapter.hold_stock("SKU-1", 2, reservation_id=1)
    assert ref == "WH-123"


@pytest.mark.asyncio
async def test_hold_stock_timeout_raises_provider_timeout():
    with respx.mock(base_url="http://fake-wh") as mock:
        mock.post("/holds").mock(side_effect=httpx.TimeoutException("timed out"))
        adapter = ExternalHttpProviderAdapter(_make_provider())
        with pytest.raises(ProviderTimeout):
            await adapter.hold_stock("SKU-1", 2, reservation_id=1)


@pytest.mark.asyncio
async def test_hold_stock_5xx_raises_provider_unavailable():
    with respx.mock(base_url="http://fake-wh") as mock:
        mock.post("/holds").mock(return_value=httpx.Response(503))
        adapter = ExternalHttpProviderAdapter(_make_provider())
        with pytest.raises(ProviderUnavailable):
            await adapter.hold_stock("SKU-1", 2, reservation_id=1)


@pytest.mark.asyncio
async def test_hold_stock_409_raises_insufficient_provider_stock():
    with respx.mock(base_url="http://fake-wh") as mock:
        mock.post("/holds").mock(
            return_value=httpx.Response(409, json={"detail": "out of stock"})
        )
        adapter = ExternalHttpProviderAdapter(_make_provider())
        with pytest.raises(InsufficientProviderStock):
            await adapter.hold_stock("SKU-1", 2, reservation_id=1)


@pytest.mark.asyncio
async def test_hold_stock_unsupported_capability_raises():
    adapter = ExternalHttpProviderAdapter(
        _make_provider(capabilities={"check_stock": True, "hold_stock": False})
    )
    with pytest.raises(CapabilityNotSupported):
        await adapter.hold_stock("SKU-1", 1, reservation_id=1)


@pytest.mark.asyncio
async def test_release_hold_failure_returns_false():
    with respx.mock(base_url="http://fake-wh") as mock:
        mock.delete("/holds/WH-123").mock(side_effect=httpx.TimeoutException("timeout"))
        adapter = ExternalHttpProviderAdapter(_make_provider())
        result = await adapter.release_hold("WH-123")
    assert result is False


@pytest.mark.asyncio
async def test_check_stock_success():
    with respx.mock(base_url="http://fake-wh") as mock:
        mock.get("/stock/SKU-1").mock(
            return_value=httpx.Response(200, json={"qty": 42})
        )
        adapter = ExternalHttpProviderAdapter(_make_provider())
        qty = await adapter.check_stock("SKU-1")
    assert qty == 42


@pytest.mark.asyncio
async def test_auth_header_api_key_injected():
    with respx.mock(base_url="http://fake-wh") as mock:
        route = mock.get("/stock/SKU-1").mock(
            return_value=httpx.Response(200, json={"qty": 5})
        )
        adapter = ExternalHttpProviderAdapter(_make_provider())
        await adapter.check_stock("SKU-1")
    assert route.calls[0].request.headers.get("x-key") == "test-key"

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NotFoundError
from app.repositories.order_repository import OrderRepository
from app.services.order_service import OrderService


def _build_service(order=None):
    repo = AsyncMock(spec=OrderRepository)
    repo.get_by_id = AsyncMock(return_value=order)
    return OrderService(order_repo=repo), repo


@pytest.mark.asyncio
async def test_get_by_id_found():
    stub_order = SimpleNamespace(id=1, reservation_id=1, user_id="u1", status="created")
    svc, _ = _build_service(order=stub_order)
    result = await svc.get_by_id(1)
    assert result is stub_order


@pytest.mark.asyncio
async def test_get_by_id_not_found_raises():
    svc, _ = _build_service(order=None)
    with pytest.raises(NotFoundError):
        await svc.get_by_id(99)

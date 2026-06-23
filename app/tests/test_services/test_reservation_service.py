from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    InsufficientStockError,
    ReservationNotFound,
    ReservationStateError,
)
from app.models.order import Order, OrderStatus
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_item import ProviderItemStatus, ReservationItem
from app.models.inventory_provider import ProviderType
from app.providers.base import InsufficientProviderStock, ProviderTimeout, ProviderUnavailable
from app.providers.registry import ProviderRegistry
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.reservation_repository import ReservationRepository
from app.services.reservation_service import ReservationService


# ── Helpers — use SimpleNamespace to avoid SQLAlchemy mapper descriptor issues ─

def _make_product(pid: int = 1, sku: str = "TEST-SKU"):
    return SimpleNamespace(id=pid, sku=sku, name="Test Product")


def _make_provider(ptype: ProviderType = ProviderType.internal):
    return SimpleNamespace(
        id=1, name="TestProvider", type=ptype, base_url="http://fake",
        timeout_seconds=5,
        capabilities={"check_stock": True, "hold_stock": True, "release_hold": True, "confirm_hold": True},
        auth_config={},
    )


def _make_inventory(qty_available: int = 10, qty_reserved: int = 0):
    return SimpleNamespace(
        id=1, product_id=1, provider_id=1,
        qty_available=qty_available, qty_reserved=qty_reserved,
        product=_make_product(), provider=_make_provider(),
        last_synced_at=None,
    )


def _make_reservation(
    rid: int = 1,
    status: ReservationStatus = ReservationStatus.pending,
    expires_delta_minutes: int = 15,
    items: list | None = None,
):
    return SimpleNamespace(
        id=rid, user_id="usr_test", status=status,
        expires_at=datetime.now(UTC) + timedelta(minutes=expires_delta_minutes),
        items=items or [],
    )


def _make_item(
    inventory_id: int = 1,
    qty: int = 2,
    provider_status: ProviderItemStatus = ProviderItemStatus.held,
    hold_ref: str | None = "hold-ref-1",
):
    return SimpleNamespace(
        id=1, reservation_id=1, product_id=1, inventory_id=inventory_id, provider_id=1,
        qty_requested=qty, provider_hold_ref=hold_ref,
        provider_status=provider_status, provider_error_message=None,
        provider=_make_provider(),
    )


def _build_service(
    inv=None,
    reservation=None,
    order=None,
    mock_adapter=None,
) -> tuple[ReservationService, AsyncMock, AsyncMock, AsyncMock]:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    inv_repo = AsyncMock(spec=InventoryRepository)
    inv_repo.db = db
    if inv is not None:
        inv_repo.get_best_available.return_value = inv
        inv_repo.get_by_id_for_update.return_value = inv

    res_repo = AsyncMock(spec=ReservationRepository)
    res_repo.db = db
    if reservation is not None:
        res_repo.get_with_items.return_value = reservation

    order_repo = AsyncMock(spec=OrderRepository)
    order_repo.db = db
    order_repo.get_by_reservation_id.return_value = None

    registry = MagicMock(spec=ProviderRegistry)
    if mock_adapter is not None:
        registry.resolve.return_value = mock_adapter

    svc = ReservationService(
        inv_repo=inv_repo,
        res_repo=res_repo,
        order_repo=order_repo,
        registry=registry,
    )
    return svc, inv_repo, res_repo, order_repo


# ── create() ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_success_internal_provider():
    inv = _make_inventory(qty_available=10, qty_reserved=0)
    mock_adapter = AsyncMock()
    mock_adapter.hold_stock = AsyncMock(return_value=None)

    created_items: list = []

    svc, inv_repo, res_repo, order_repo = _build_service(inv=inv, mock_adapter=mock_adapter)

    def fake_add(obj):
        if isinstance(obj, ReservationItem):
            obj.id = 99
            obj.provider = inv.provider
            created_items.append(obj)
        elif isinstance(obj, Reservation):
            obj.id = 1

    inv_repo.db.add.side_effect = fake_add

    async def fake_refresh(obj):
        if isinstance(obj, Reservation):
            obj.items = created_items

    inv_repo.db.refresh.side_effect = fake_refresh

    result = await svc.create(user_id="usr_test", items=[{"product_id": 1, "qty": 2}])
    assert result is not None
    assert inv.qty_reserved == 2
    assert len(created_items) == 1
    assert created_items[0].provider_status == ProviderItemStatus.held


@pytest.mark.asyncio
async def test_create_insufficient_stock_raises():
    inv = _make_inventory(qty_available=1, qty_reserved=1)
    svc, *_ = _build_service(inv=inv)
    with pytest.raises(InsufficientStockError) as exc_info:
        await svc.create(user_id="usr_test", items=[{"product_id": 1, "qty": 2}])
    assert "available 0" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_no_inventory_raises():
    svc, inv_repo, *_ = _build_service()
    inv_repo.get_best_available.return_value = None
    with pytest.raises(InsufficientStockError):
        await svc.create(user_id="usr_test", items=[{"product_id": 99, "qty": 1}])


@pytest.mark.asyncio
async def test_create_provider_timeout_marks_degraded():
    inv = _make_inventory(qty_available=10, qty_reserved=0)
    mock_adapter = AsyncMock()
    mock_adapter.hold_stock = AsyncMock(side_effect=ProviderTimeout("timeout"))

    created_items: list = []
    svc, inv_repo, *_ = _build_service(inv=inv, mock_adapter=mock_adapter)

    def fake_add(obj):
        if isinstance(obj, ReservationItem):
            obj.id = 99
            obj.provider = inv.provider
            created_items.append(obj)
        elif isinstance(obj, Reservation):
            obj.id = 1

    inv_repo.db.add.side_effect = fake_add

    async def fake_refresh(obj):
        if isinstance(obj, Reservation):
            obj.items = created_items

    inv_repo.db.refresh.side_effect = fake_refresh

    result = await svc.create(user_id="usr_test", items=[{"product_id": 1, "qty": 2}])
    assert result is not None
    assert inv.qty_reserved == 2  # local hold still applied
    assert created_items[0].provider_status == ProviderItemStatus.provider_failed
    assert created_items[0].provider_error_message is not None


@pytest.mark.asyncio
async def test_create_provider_insufficient_stock_rolls_back():
    inv = _make_inventory(qty_available=10, qty_reserved=0)
    mock_adapter = AsyncMock()
    mock_adapter.hold_stock = AsyncMock(
        side_effect=InsufficientProviderStock("out of stock")
    )

    svc, inv_repo, *_ = _build_service(inv=inv, mock_adapter=mock_adapter)
    inv_repo.db.add.side_effect = lambda obj: None

    with pytest.raises(InsufficientStockError):
        await svc.create(user_id="usr_test", items=[{"product_id": 1, "qty": 2}])


# ── confirm() ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_success():
    inv = _make_inventory(qty_available=10, qty_reserved=2)
    item = _make_item(qty=2, provider_status=ProviderItemStatus.held, hold_ref="ref-1")
    reservation = _make_reservation(items=[item])

    mock_adapter = AsyncMock()
    mock_adapter.confirm_hold = AsyncMock(return_value=True)

    svc, inv_repo, res_repo, order_repo = _build_service(
        inv=inv, reservation=reservation, mock_adapter=mock_adapter
    )

    async def fake_order_refresh(obj):
        if isinstance(obj, Order):
            obj.id = 1
            obj.reservation_id = 1
            obj.user_id = "usr_test"
            obj.status = OrderStatus.created

    inv_repo.db.refresh.side_effect = fake_order_refresh

    order = await svc.confirm(1)
    assert order is not None
    assert inv.qty_available == 8
    assert inv.qty_reserved == 0
    mock_adapter.confirm_hold.assert_called_once_with("ref-1")


@pytest.mark.asyncio
async def test_confirm_expired_raises_state_error():
    reservation = _make_reservation(expires_delta_minutes=-5)  # already expired
    svc, *_ = _build_service(reservation=reservation)
    with pytest.raises(ReservationStateError) as exc_info:
        await svc.confirm(1)
    assert "expired" in str(exc_info.value)


@pytest.mark.asyncio
async def test_confirm_already_confirmed_raises_state_error():
    reservation = _make_reservation(status=ReservationStatus.confirmed)
    svc, *_ = _build_service(reservation=reservation)
    with pytest.raises(ReservationStateError):
        await svc.confirm(1)


@pytest.mark.asyncio
async def test_confirm_skips_provider_call_when_provider_failed():
    inv = _make_inventory(qty_available=10, qty_reserved=2)
    item = _make_item(
        qty=2,
        provider_status=ProviderItemStatus.provider_failed,
        hold_ref=None,
    )
    reservation = _make_reservation(items=[item])

    mock_adapter = AsyncMock()
    svc, inv_repo, *_ = _build_service(
        inv=inv, reservation=reservation, mock_adapter=mock_adapter
    )

    async def fake_confirm_refresh(obj):
        if isinstance(obj, Order):
            obj.id = 1
            obj.status = OrderStatus.created
            obj.user_id = "usr_test"
            obj.reservation_id = 1

    inv_repo.db.refresh.side_effect = fake_confirm_refresh

    await svc.confirm(1)
    mock_adapter.confirm_hold.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_provider_confirm_failure_non_fatal():
    inv = _make_inventory(qty_available=10, qty_reserved=2)
    item = _make_item(qty=2, provider_status=ProviderItemStatus.held, hold_ref="ref-1")
    reservation = _make_reservation(items=[item])

    mock_adapter = AsyncMock()
    mock_adapter.confirm_hold = AsyncMock(side_effect=ProviderUnavailable("down"))

    svc, inv_repo, *_ = _build_service(
        inv=inv, reservation=reservation, mock_adapter=mock_adapter
    )

    async def fake_nonfatal_refresh(obj):
        if isinstance(obj, Order):
            obj.id = 1
            obj.status = OrderStatus.created
            obj.user_id = "usr_test"
            obj.reservation_id = 1

    inv_repo.db.refresh.side_effect = fake_nonfatal_refresh

    order = await svc.confirm(1)
    assert order is not None  # order still created despite provider failure


# ── cancel() ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_success():
    inv = _make_inventory(qty_available=10, qty_reserved=2)
    item = _make_item(qty=2, provider_status=ProviderItemStatus.held, hold_ref="ref-1")
    reservation = _make_reservation(items=[item])

    mock_adapter = AsyncMock()
    mock_adapter.release_hold = AsyncMock(return_value=True)

    svc, inv_repo, *_ = _build_service(
        inv=inv, reservation=reservation, mock_adapter=mock_adapter
    )

    await svc.cancel(1)
    assert reservation.status == ReservationStatus.cancelled
    assert inv.qty_reserved == 0
    mock_adapter.release_hold.assert_called_once_with("ref-1")


@pytest.mark.asyncio
async def test_cancel_idempotent_on_already_cancelled():
    reservation = _make_reservation(status=ReservationStatus.cancelled, items=[])
    svc, inv_repo, *_ = _build_service(reservation=reservation)
    await svc.cancel(1)  # should not raise
    inv_repo.get_by_id_for_update.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_skips_release_when_no_hold_ref():
    inv = _make_inventory(qty_available=10, qty_reserved=2)
    item = _make_item(
        qty=2,
        provider_status=ProviderItemStatus.held,
        hold_ref=None,
    )
    reservation = _make_reservation(items=[item])
    mock_adapter = AsyncMock()

    svc, *_ = _build_service(inv=inv, reservation=reservation, mock_adapter=mock_adapter)
    await svc.cancel(1)
    mock_adapter.release_hold.assert_not_called()


# ── expire_batch() ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_expire_batch_finds_expired_reservations():
    inv = _make_inventory(qty_available=10, qty_reserved=2)
    item = _make_item(qty=2, provider_status=ProviderItemStatus.held, hold_ref=None)
    expired_res = _make_reservation(items=[item], expires_delta_minutes=-10)

    svc, inv_repo, res_repo, *_ = _build_service(inv=inv)
    res_repo.get_expired_pending.return_value = [expired_res]

    count = await svc.expire_batch()
    assert count == 1
    assert expired_res.status == ReservationStatus.expired


@pytest.mark.asyncio
async def test_expire_batch_releases_qty_reserved():
    inv = _make_inventory(qty_available=10, qty_reserved=3)
    item = _make_item(qty=3, provider_status=ProviderItemStatus.held, hold_ref=None)
    expired_res = _make_reservation(items=[item], expires_delta_minutes=-10)

    svc, inv_repo, res_repo, *_ = _build_service(inv=inv)
    res_repo.get_expired_pending.return_value = [expired_res]

    await svc.expire_batch()
    assert inv.qty_reserved == 0


@pytest.mark.asyncio
async def test_expire_batch_respects_limit():
    svc, inv_repo, res_repo, *_ = _build_service()
    res_repo.get_expired_pending.return_value = []
    await svc.expire_batch(limit=10)
    res_repo.get_expired_pending.assert_called_once_with(10)

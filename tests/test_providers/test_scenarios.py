"""
Required provider integration scenarios (spec: inventory-provider-adapter).

Scenario A — Happy path: External provider hold succeeds → hold_ref persisted →
             confirm_hold called on confirmation → inventory consumed.

Scenario B — Timeout path: External provider times out during hold → reservation
             created in degraded state (provider_failed) → confirm skips provider
             call → inventory consumed locally.
"""
from types import SimpleNamespace

import httpx
import pytest
import respx
from unittest.mock import AsyncMock, MagicMock

from app.models.inventory_provider import ProviderType
from app.models.order import Order, OrderStatus
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_item import ProviderItemStatus, ReservationItem
from app.providers.registry import ProviderRegistry
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.reservation_repository import ReservationRepository
from app.services.reservation_service import ReservationService


def _make_external_provider():
    return SimpleNamespace(
        id=2, name="WarehouseProvider", type=ProviderType.external,
        base_url="http://fake-wh", timeout_seconds=5,
        capabilities={
            "check_stock": True, "hold_stock": True,
            "release_hold": True, "confirm_hold": True,
        },
        auth_config={},
    )


def _make_product():
    return SimpleNamespace(id=1, sku="SONY-WH-XM5-BLK", name="Sony WH-1000XM5")


def _make_inventory(provider, product):
    return SimpleNamespace(
        id=1, product_id=product.id, provider_id=provider.id,
        qty_available=10, qty_reserved=0,
        provider=provider, product=product, last_synced_at=None,
    )


def _build_service(inv_repo, res_repo, order_repo, registry) -> ReservationService:
    return ReservationService(
        inv_repo=inv_repo,
        res_repo=res_repo,
        order_repo=order_repo,
        registry=registry,
    )


# ── Scenario A — Happy Path ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_a_provider_hold_and_confirm_succeeds():
    """
    GIVEN: product with external provider that supports hold_stock
    WHEN:  reservation created — provider returns hold_ref
    THEN:  reservation_item.provider_status = held, hold_ref = "WH-abc123"
    WHEN:  reservation confirmed
    THEN:  provider confirm_hold called, inventory consumed, order created
    """
    provider = _make_external_provider()
    product = _make_product()
    inv = _make_inventory(provider, product)

    # ── Mock repos ────────────────────────────────────────────────────────────
    inv_repo = AsyncMock(spec=InventoryRepository)
    inv_repo.db = AsyncMock()
    inv_repo.db.add = MagicMock()
    inv_repo.db.flush = AsyncMock()
    inv_repo.db.refresh = AsyncMock()
    inv_repo.get_best_available.return_value = inv
    inv_repo.get_by_id_for_update.return_value = inv

    from datetime import UTC, datetime, timedelta

    created_items: list[ReservationItem] = []

    reservation = SimpleNamespace(
        id=42, user_id="usr_001", status=ReservationStatus.pending,
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
        items=created_items,
    )

    def fake_add(obj):
        if isinstance(obj, ReservationItem):
            obj.id = len(created_items) + 1
            obj.provider = provider  # populate relationship — no real DB session
            created_items.append(obj)
        elif isinstance(obj, Reservation):
            obj.id = 42

    inv_repo.db.add.side_effect = fake_add

    async def fake_db_refresh(obj):
        if isinstance(obj, Reservation):
            obj.items = created_items

    inv_repo.db.refresh.side_effect = fake_db_refresh

    res_repo = AsyncMock(spec=ReservationRepository)
    res_repo.db = inv_repo.db
    res_repo.get_with_items.return_value = reservation

    order_repo = AsyncMock(spec=OrderRepository)
    order_repo.db = inv_repo.db
    order_repo.get_by_reservation_id.return_value = None
    order_repo.db.add = inv_repo.db.add

    async def fake_order_refresh(obj):
        if isinstance(obj, Order):
            obj.id = 1
            obj.reservation_id = 42
            obj.user_id = "usr_001"
            obj.status = OrderStatus.created

    order_repo.db.refresh.side_effect = fake_order_refresh

    with respx.mock(base_url="http://fake-wh") as mock:
        hold_route = mock.post("/holds").mock(
            return_value=httpx.Response(200, json={"hold_ref": "WH-abc123"})
        )
        confirm_route = mock.post("/holds/WH-abc123/confirm").mock(
            return_value=httpx.Response(200, json={"status": "confirmed"})
        )

        registry = ProviderRegistry()
        svc = _build_service(inv_repo, res_repo, order_repo, registry)

        # Create
        result = await svc.create(user_id="usr_001", items=[{"product_id": 1, "qty": 2}])
        assert result is not None
        assert len(created_items) == 1
        item = created_items[0]
        assert item.provider_status == ProviderItemStatus.held
        assert item.provider_hold_ref == "WH-abc123"
        assert hold_route.called

        # Confirm
        from datetime import UTC, datetime, timedelta
        reservation.expires_at = datetime.now(UTC) + timedelta(minutes=15)
        reservation.status = ReservationStatus.pending

        order = await svc.confirm(42)
        assert order is not None
        assert confirm_route.called


# ── Scenario B — Provider Timeout ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_b_provider_hold_timeout_reservation_degraded():
    """
    GIVEN: product with external provider that supports hold_stock
    WHEN:  reservation created BUT provider call times out
    THEN:  reservation still created, item.provider_status = provider_failed,
           item.provider_error_message set, qty_reserved still incremented
    WHEN:  reservation confirmed
    THEN:  provider confirm_hold NOT called, inventory consumed locally, order created
    """
    provider = _make_external_provider()
    product = _make_product()
    inv = _make_inventory(provider, product)

    inv_repo = AsyncMock(spec=InventoryRepository)
    inv_repo.db = AsyncMock()
    inv_repo.db.add = MagicMock()
    inv_repo.db.flush = AsyncMock()
    inv_repo.db.refresh = AsyncMock()
    inv_repo.get_best_available.return_value = inv
    inv_repo.get_by_id_for_update.return_value = inv

    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace as NS

    created_items: list[ReservationItem] = []

    def fake_add(obj):
        if isinstance(obj, ReservationItem):
            obj.id = 99
            obj.provider = provider
            created_items.append(obj)
        elif isinstance(obj, Reservation):
            obj.id = 43

    inv_repo.db.add.side_effect = fake_add

    reservation = NS(
        id=43, user_id="usr_002", status=ReservationStatus.pending,
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
        items=created_items,
    )

    async def fake_refresh(obj):
        if isinstance(obj, Reservation):
            obj.items = created_items

    inv_repo.db.refresh.side_effect = fake_refresh

    res_repo = AsyncMock(spec=ReservationRepository)
    res_repo.db = inv_repo.db
    res_repo.get_with_items.return_value = reservation

    order_repo = AsyncMock(spec=OrderRepository)
    order_repo.db = inv_repo.db
    order_repo.get_by_reservation_id.return_value = None
    order_repo.db.add = inv_repo.db.add

    async def fake_order_refresh(obj):
        if isinstance(obj, Order):
            obj.id = 2
            obj.reservation_id = 43
            obj.user_id = "usr_002"
            obj.status = OrderStatus.created

    order_repo.db.refresh.side_effect = fake_order_refresh

    with respx.mock(base_url="http://fake-wh") as mock:
        mock.post("/holds").mock(side_effect=httpx.TimeoutException("timed out"))

        registry = ProviderRegistry()
        svc = _build_service(inv_repo, res_repo, order_repo, registry)

        # Create — should succeed despite timeout
        result = await svc.create(user_id="usr_002", items=[{"product_id": 1, "qty": 1}])
        assert result is not None

        item = created_items[0]
        assert item.provider_status == ProviderItemStatus.provider_failed
        assert item.provider_error_message is not None
        assert "timed out" in item.provider_error_message.lower() or \
               "timeout" in item.provider_error_message.lower()
        assert item.provider_hold_ref is None

    # Confirm — provider confirm should NOT be called (item was provider_failed)
    from datetime import UTC, datetime, timedelta
    reservation.expires_at = datetime.now(UTC) + timedelta(minutes=15)
    reservation.status = ReservationStatus.pending

    with respx.mock(base_url="http://fake-wh") as mock:
        order = await svc.confirm(43)
        assert order is not None
        # Verify no confirm call was made
        assert len(mock.calls) == 0

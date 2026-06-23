from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.models.inventory_provider import InventoryProvider, ProviderType
from app.models.product import Product
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_item import ReservationItem
from app.repositories.reservation_repository import ReservationRepository

# ── Seed helpers ──────────────────────────────────────────────────────────────

async def _seed_reservation(
    db: AsyncSession,
    status: ReservationStatus = ReservationStatus.pending,
    expires_delta: timedelta = timedelta(hours=1),
) -> Reservation:
    now = datetime.now(UTC)
    r = Reservation(
        user_id="user_test",
        status=status,
        expires_at=now + expires_delta,
        created_at=now,
        updated_at=now,
    )
    db.add(r)
    await db.flush()
    return r


async def _seed_prerequisites(db: AsyncSession):
    now = datetime.now(UTC)
    product = Product(name="Prod", sku="SKU-R1", created_at=now, updated_at=now)
    provider = InventoryProvider(
        name="WH-R", type=ProviderType.external, capabilities={},
        is_active=True, created_at=now, updated_at=now,
    )
    db.add(product)
    db.add(provider)
    await db.flush()
    inv = Inventory(
        product_id=product.id, provider_id=provider.id,
        qty_available=10, qty_reserved=0, created_at=now, updated_at=now,
    )
    db.add(inv)
    await db.flush()
    return product, provider, inv


async def _seed_item(
    db: AsyncSession, reservation: Reservation,
    product_id: int, provider_id: int, inventory_id: int,
) -> ReservationItem:
    now = datetime.now(UTC)
    item = ReservationItem(
        reservation_id=reservation.id,
        product_id=product_id,
        provider_id=provider_id,
        inventory_id=inventory_id,
        qty_requested=2,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    await db.flush()
    return item


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_with_items_loads_reservation_and_items(db_session: AsyncSession):
    res = await _seed_reservation(db_session)
    product, provider, inv = await _seed_prerequisites(db_session)
    await _seed_item(db_session, res, product.id, provider.id, inv.id)

    repo = ReservationRepository(db_session)
    loaded = await repo.get_with_items(res.id)
    assert loaded is not None
    assert loaded.id == res.id
    assert len(loaded.items) == 1


@pytest.mark.asyncio
async def test_get_with_items_returns_none_for_unknown(db_session: AsyncSession):
    repo = ReservationRepository(db_session)
    result = await repo.get_with_items(reservation_id=9999)
    assert result is None


@pytest.mark.asyncio
async def test_get_expired_pending_returns_past_pending(db_session: AsyncSession):
    # pending + expired
    expired = await _seed_reservation(db_session, expires_delta=timedelta(hours=-1))
    # pending + not yet expired
    await _seed_reservation(db_session, expires_delta=timedelta(hours=1))
    # confirmed + expired
    await _seed_reservation(
        db_session, status=ReservationStatus.confirmed, expires_delta=timedelta(hours=-1)
    )

    repo = ReservationRepository(db_session)
    results = await repo.get_expired_pending(limit=10)
    ids = [r.id for r in results]
    assert expired.id in ids
    assert len(results) == 1


@pytest.mark.asyncio
async def test_get_expired_pending_respects_limit(db_session: AsyncSession):
    for _ in range(5):
        await _seed_reservation(db_session, expires_delta=timedelta(hours=-1))

    repo = ReservationRepository(db_session)
    results = await repo.get_expired_pending(limit=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_get_expired_pending_empty_when_none_expired(db_session: AsyncSession):
    await _seed_reservation(db_session, expires_delta=timedelta(hours=1))

    repo = ReservationRepository(db_session)
    results = await repo.get_expired_pending(limit=10)
    assert results == []

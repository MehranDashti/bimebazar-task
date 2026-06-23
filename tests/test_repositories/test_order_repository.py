from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.reservation import Reservation, ReservationStatus
from app.repositories.order_repository import OrderRepository

# ── Seed helpers ──────────────────────────────────────────────────────────────

async def _seed_reservation(db: AsyncSession) -> Reservation:
    now = datetime.now(UTC)
    r = Reservation(
        user_id="user_order",
        status=ReservationStatus.confirmed,
        expires_at=now + timedelta(hours=1),
        created_at=now,
        updated_at=now,
    )
    db.add(r)
    await db.flush()
    return r


async def _seed_order(db: AsyncSession, reservation: Reservation) -> Order:
    now = datetime.now(UTC)
    o = Order(
        reservation_id=reservation.id,
        user_id="user_order",
        status=OrderStatus.created,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    await db.flush()
    return o


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_by_reservation_id_found(db_session: AsyncSession):
    res = await _seed_reservation(db_session)
    order = await _seed_order(db_session, res)

    repo = OrderRepository(db_session)
    result = await repo.get_by_reservation_id(res.id)
    assert result is not None
    assert result.id == order.id
    assert result.reservation_id == res.id


@pytest.mark.asyncio
async def test_get_by_reservation_id_not_found(db_session: AsyncSession):
    repo = OrderRepository(db_session)
    result = await repo.get_by_reservation_id(reservation_id=9999)
    assert result is None

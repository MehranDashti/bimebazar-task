from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_item import ReservationItem
from app.repositories.base import BaseRepository


class ReservationRepository(BaseRepository[Reservation]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Reservation, db)

    async def get_with_items(self, reservation_id: int) -> Reservation | None:
        result = await self.db.execute(
            select(Reservation)
            .where(Reservation.id == reservation_id)
            .options(
                selectinload(Reservation.items)
            )
        )
        return result.scalars().first()

    async def get_expired_pending(self, limit: int = 100) -> list[Reservation]:
        """SELECT pending reservations past their TTL, with SKIP LOCKED for multi-replica safety."""
        result = await self.db.execute(
            select(Reservation)
            .where(
                Reservation.status == ReservationStatus.pending,
                Reservation.expires_at < datetime.now(UTC),
            )
            .options(selectinload(Reservation.items))
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        return list(result.scalars().all())

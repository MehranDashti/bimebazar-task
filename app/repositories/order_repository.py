from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Order, db)

    async def get_by_reservation_id(self, reservation_id: int) -> Order | None:
        result = await self.db.execute(
            select(Order).where(Order.reservation_id == reservation_id)
        )
        return result.scalars().first()

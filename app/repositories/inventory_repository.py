from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.repositories.base import BaseRepository


class InventoryRepository(BaseRepository[Inventory]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Inventory, db)

    async def get_by_product_for_update(self, product_id: int) -> Inventory | None:
        result = await self.db.execute(
            select(Inventory)
            .where(Inventory.product_id == product_id)
            .with_for_update()
        )
        return result.scalars().first()

    async def get_best_available(self, product_id: int) -> Inventory | None:
        """Return the inventory row with the highest effective available qty."""
        result = await self.db.execute(
            select(Inventory)
            .where(Inventory.product_id == product_id)
            .order_by(
                (Inventory.qty_available - Inventory.qty_reserved).desc()
            )
            .limit(1)
        )
        return result.scalars().first()

    async def get_by_id_for_update(self, inventory_id: int) -> Inventory | None:
        result = await self.db.execute(
            select(Inventory)
            .where(Inventory.id == inventory_id)
            .with_for_update()
        )
        return result.scalars().first()

    async def get_all_by_provider(self, provider_id: int) -> list[Inventory]:
        result = await self.db.execute(
            select(Inventory).where(Inventory.provider_id == provider_id)
        )
        return list(result.scalars().all())

    async def get_all_by_product(self, product_id: int) -> list[Inventory]:
        result = await self.db.execute(
            select(Inventory).where(Inventory.product_id == product_id)
        )
        return list(result.scalars().all())

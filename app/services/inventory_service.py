import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.inventory import Inventory
from app.models.inventory_provider import InventoryProvider, ProviderType
from app.providers.base import ProviderError
from app.providers.registry import ProviderRegistry
from app.repositories.inventory_repository import InventoryRepository

logger = logging.getLogger(__name__)


class InventoryService:
    def __init__(self, inv_repo: InventoryRepository) -> None:
        self._inv_repo = inv_repo

    async def get_availability(self, product_id: int) -> dict:
        rows = await self._inv_repo.get_all_by_product(product_id)
        sources = [
            {
                "provider_id": row.provider_id,
                "provider_name": row.provider.name if row.provider else "unknown",
                "qty_available": row.qty_available,
                "qty_reserved": row.qty_reserved,
                "effective_available": row.qty_available - row.qty_reserved,
                "last_synced_at": row.last_synced_at,
            }
            for row in rows
        ]
        return {"product_id": product_id, "sources": sources}

    async def sync_from_provider(self, provider_id: int) -> dict:
        db = self._inv_repo.db
        result = await db.execute(
            select(InventoryProvider).where(InventoryProvider.id == provider_id)
        )
        provider = result.scalars().first()
        if provider is None:
            raise NotFoundError(f"Provider {provider_id} not found")

        if not provider.is_active:
            raise ValueError(f"Provider {provider_id} is inactive")

        if provider.type == ProviderType.internal:
            return {"updated": 0, "errors": [], "message": "internal providers do not require sync"}

        rows = await self._inv_repo.get_all_by_provider(provider_id)
        updated = 0
        errors: list[str] = []

        for row in rows:
            sku = row.product.sku if row.product else None
            if not sku:
                continue
            adapter = ProviderRegistry.resolve(provider)
            try:
                qty = await adapter.check_stock(sku)
                row.qty_available = qty
                row.last_synced_at = datetime.now(UTC)
                updated += 1
            except ProviderError as exc:
                logger.warning("sync_from_provider: sku=%s error=%s", sku, exc)
                errors.append(f"{sku}: {exc}")

        await db.flush()
        return {"updated": updated, "errors": errors}

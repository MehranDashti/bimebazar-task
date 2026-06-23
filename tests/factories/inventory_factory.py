import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.models.inventory_provider import InventoryProvider, ProviderType
from app.models.product import Product


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def make_product(
    db: AsyncSession,
    *,
    name: str | None = None,
    sku: str | None = None,
) -> Product:
    now = datetime.now(UTC)
    product = Product(
        name=name or f"Product {_uid()}",
        sku=sku or f"SKU-{_uid()}",
        created_at=now,
        updated_at=now,
    )
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


async def make_provider(
    db: AsyncSession,
    *,
    name: str | None = None,
    type: ProviderType = ProviderType.external,
    base_url: str = "http://warehouse.example.com",
    is_active: bool = True,
) -> InventoryProvider:
    now = datetime.now(UTC)
    provider = InventoryProvider(
        name=name or f"Provider {_uid()}",
        type=type,
        capabilities={},
        base_url=base_url if type == ProviderType.external else None,
        auth_config={"api_key": "test-key"} if type == ProviderType.external else None,
        timeout_seconds=5,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(provider)
    await db.flush()
    await db.refresh(provider)
    return provider


async def make_inventory(
    db: AsyncSession,
    *,
    product: Product | None = None,
    provider: InventoryProvider | None = None,
    qty_available: int = 10,
    qty_reserved: int = 0,
) -> Inventory:
    if product is None:
        product = await make_product(db)
    if provider is None:
        provider = await make_provider(db)
    now = datetime.now(UTC)
    inventory = Inventory(
        product_id=product.id,
        provider_id=provider.id,
        qty_available=qty_available,
        qty_reserved=qty_reserved,
        created_at=now,
        updated_at=now,
    )
    db.add(inventory)
    await db.flush()
    await db.refresh(inventory)
    return inventory

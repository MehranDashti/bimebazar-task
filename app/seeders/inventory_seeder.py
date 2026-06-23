from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.models.inventory_provider import InventoryProvider, ProviderType
from app.models.product import Product

from .base import BaseSeeder


class InventorySeeder(BaseSeeder):
    name = "inventory"
    description = "Seed inventory providers, products, and stock levels"

    async def run(self, db: AsyncSession) -> None:
        # --- Providers ---
        internal = await self._get_or_create_provider(
            db,
            name="InternalStock",
            type=ProviderType.internal,
            capabilities={
                "check_stock": True,
                "hold_stock": True,
                "release_hold": True,
                "confirm_hold": True,
            },
        )

        external = await self._get_or_create_provider(
            db,
            name="WarehouseProvider",
            type=ProviderType.external,
            base_url="http://warehouse-api.example.com",
            timeout_seconds=5,
            capabilities={
                "check_stock": True,
                "hold_stock": True,
                "release_hold": True,
                "confirm_hold": True,
            },
            auth_config={
                "type": "api_key",
                "header": "X-Warehouse-Key",
                "value": "dev-key-change-in-production",
            },
        )

        # --- Products ---
        sony = await self._get_or_create_product(
            db, name="Sony WH-1000XM5 Headphones", sku="SONY-WH-XM5-BLK"
        )
        anker = await self._get_or_create_product(
            db, name="Anker USB-C Hub 7-in-1", sku="ANKR-HUB-7C"
        )

        # --- Inventory rows ---
        await self._get_or_create_inventory(
            db, product_id=sony.id, provider_id=external.id, qty_available=12
        )
        await self._get_or_create_inventory(
            db, product_id=anker.id, provider_id=internal.id, qty_available=340
        )

    async def _get_or_create_provider(
        self, db: AsyncSession, name: str, **kwargs: object
    ) -> InventoryProvider:
        result = await db.execute(
            select(InventoryProvider).where(InventoryProvider.name == name)
        )
        provider = result.scalars().first()
        if provider:
            print(f"   — exists   provider:{name}")
            return provider
        provider = InventoryProvider(name=name, **kwargs)  # type: ignore[arg-type]
        db.add(provider)
        await db.flush()
        print(f"   ✔ created  provider:{name}")
        return provider

    async def _get_or_create_product(
        self, db: AsyncSession, name: str, sku: str
    ) -> Product:
        result = await db.execute(select(Product).where(Product.sku == sku))
        product = result.scalars().first()
        if product:
            print(f"   — exists   product:{sku}")
            return product
        product = Product(name=name, sku=sku)
        db.add(product)
        await db.flush()
        print(f"   ✔ created  product:{sku}")
        return product

    async def _get_or_create_inventory(
        self,
        db: AsyncSession,
        product_id: int,
        provider_id: int,
        qty_available: int,
    ) -> Inventory:
        result = await db.execute(
            select(Inventory).where(
                Inventory.product_id == product_id,
                Inventory.provider_id == provider_id,
            )
        )
        inv = result.scalars().first()
        if inv:
            print(f"   — exists   inventory:product={product_id}/provider={provider_id}")
            return inv
        inv = Inventory(
            product_id=product_id,
            provider_id=provider_id,
            qty_available=qty_available,
            qty_reserved=0,
        )
        db.add(inv)
        await db.flush()
        print(
            f"   ✔ created  inventory:product={product_id}"
            f"/provider={provider_id} qty={qty_available}"
        )
        return inv

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.models.inventory_provider import InventoryProvider, ProviderType
from app.models.product import Product
from app.repositories.inventory_repository import InventoryRepository


# ── Seed helpers ──────────────────────────────────────────────────────────────

async def _seed_product(db: AsyncSession, sku: str = "SKU-001") -> Product:
    now = datetime.now(UTC)
    p = Product(name="Test Product", sku=sku, created_at=now, updated_at=now)
    db.add(p)
    await db.flush()
    return p


async def _seed_provider(db: AsyncSession, name: str = "WH") -> InventoryProvider:
    now = datetime.now(UTC)
    prov = InventoryProvider(
        name=name, type=ProviderType.external, capabilities={},
        is_active=True, created_at=now, updated_at=now,
    )
    db.add(prov)
    await db.flush()
    return prov


async def _seed_inventory(
    db: AsyncSession,
    product_id: int,
    provider_id: int,
    qty_available: int = 10,
    qty_reserved: int = 0,
) -> Inventory:
    now = datetime.now(UTC)
    inv = Inventory(
        product_id=product_id, provider_id=provider_id,
        qty_available=qty_available, qty_reserved=qty_reserved,
        created_at=now, updated_at=now,
    )
    db.add(inv)
    await db.flush()
    return inv


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_best_available_returns_highest_effective(db_session: AsyncSession):
    product = await _seed_product(db_session)
    prov1 = await _seed_provider(db_session, "P1")
    prov2 = await _seed_provider(db_session, "P2")
    # prov1: effective = 10 - 8 = 2
    # prov2: effective = 10 - 0 = 10  ← winner
    await _seed_inventory(db_session, product.id, prov1.id, qty_available=10, qty_reserved=8)
    await _seed_inventory(db_session, product.id, prov2.id, qty_available=10, qty_reserved=0)

    repo = InventoryRepository(db_session)
    result = await repo.get_best_available(product.id)
    assert result is not None
    assert result.provider_id == prov2.id


@pytest.mark.asyncio
async def test_get_best_available_returns_none_when_no_inventory(db_session: AsyncSession):
    repo = InventoryRepository(db_session)
    result = await repo.get_best_available(product_id=9999)
    assert result is None


@pytest.mark.asyncio
async def test_get_all_by_provider_returns_rows(db_session: AsyncSession):
    product = await _seed_product(db_session)
    prov = await _seed_provider(db_session)
    await _seed_inventory(db_session, product.id, prov.id, qty_available=5)

    repo = InventoryRepository(db_session)
    rows = await repo.get_all_by_provider(prov.id)
    assert len(rows) == 1
    assert rows[0].provider_id == prov.id


@pytest.mark.asyncio
async def test_get_all_by_provider_empty_for_unknown(db_session: AsyncSession):
    repo = InventoryRepository(db_session)
    rows = await repo.get_all_by_provider(provider_id=9999)
    assert rows == []


@pytest.mark.asyncio
async def test_get_all_by_product_returns_all_rows(db_session: AsyncSession):
    product = await _seed_product(db_session)
    prov1 = await _seed_provider(db_session, "P1")
    prov2 = await _seed_provider(db_session, "P2")
    await _seed_inventory(db_session, product.id, prov1.id)
    await _seed_inventory(db_session, product.id, prov2.id)

    repo = InventoryRepository(db_session)
    rows = await repo.get_all_by_product(product.id)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_get_by_id_for_update_found(db_session: AsyncSession):
    product = await _seed_product(db_session)
    prov = await _seed_provider(db_session)
    inv = await _seed_inventory(db_session, product.id, prov.id, qty_available=7)

    repo = InventoryRepository(db_session)
    result = await repo.get_by_id_for_update(inv.id)
    assert result is not None
    assert result.qty_available == 7


@pytest.mark.asyncio
async def test_get_by_id_for_update_not_found(db_session: AsyncSession):
    repo = InventoryRepository(db_session)
    result = await repo.get_by_id_for_update(inventory_id=9999)
    assert result is None

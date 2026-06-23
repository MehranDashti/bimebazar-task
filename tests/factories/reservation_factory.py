from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.models.inventory_provider import InventoryProvider
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_item import ProviderItemStatus, ReservationItem
from tests.factories.inventory_factory import make_inventory, make_product, make_provider


async def make_reservation(
    db: AsyncSession,
    *,
    user_id: str = "user_test",
    status: ReservationStatus = ReservationStatus.pending,
    expires_delta: timedelta = timedelta(minutes=15),
) -> Reservation:
    now = datetime.now(UTC)
    reservation = Reservation(
        user_id=user_id,
        status=status,
        expires_at=now + expires_delta,
        created_at=now,
        updated_at=now,
    )
    db.add(reservation)
    await db.flush()
    await db.refresh(reservation)
    return reservation


async def make_reservation_item(
    db: AsyncSession,
    reservation: Reservation,
    *,
    product: Product | None = None,
    provider: InventoryProvider | None = None,
    inventory: Inventory | None = None,
    qty_requested: int = 1,
    provider_status: ProviderItemStatus = ProviderItemStatus.pending,
    provider_hold_ref: str | None = None,
) -> ReservationItem:
    if inventory is None:
        inventory = await make_inventory(
            db,
            product=product,
            provider=provider,
            qty_available=10,
            qty_reserved=qty_requested,
        )
    now = datetime.now(UTC)
    item = ReservationItem(
        reservation_id=reservation.id,
        product_id=inventory.product_id,
        provider_id=inventory.provider_id,
        inventory_id=inventory.id,
        qty_requested=qty_requested,
        provider_status=provider_status,
        provider_hold_ref=provider_hold_ref,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def make_order(
    db: AsyncSession,
    reservation: Reservation,
    *,
    user_id: str | None = None,
    status: OrderStatus = OrderStatus.created,
) -> Order:
    now = datetime.now(UTC)
    order = Order(
        reservation_id=reservation.id,
        user_id=user_id or reservation.user_id,
        status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(order)
    await db.flush()
    await db.refresh(order)
    return order

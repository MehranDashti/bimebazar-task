from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.exceptions import (
    DuplicateOrderError,
    InsufficientStockError,
    ReservationNotFound,
    ReservationStateError,
)
from app.models.inventory import Inventory
from app.models.order import Order, OrderStatus
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_item import ProviderItemStatus, ReservationItem
from app.providers.base import (
    InsufficientProviderStock,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.registry import ProviderRegistry
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.reservation_repository import ReservationRepository


class ReservationService:
    def __init__(
        self,
        inv_repo: InventoryRepository,
        res_repo: ReservationRepository,
        order_repo: OrderRepository,
        registry: ProviderRegistry,
    ) -> None:
        self._inv_repo = inv_repo
        self._res_repo = res_repo
        self._order_repo = order_repo
        self._registry = registry

    async def create(
        self, user_id: str, items: list[dict]
    ) -> Reservation:
        """
        Reserve inventory for all items atomically.
        - Uses SELECT FOR UPDATE on each inventory row to prevent concurrent oversell.
        - Fail-open on provider timeout/unavailable: reservation created in degraded state.
        - Fail-closed on InsufficientProviderStock: entire reservation rolled back.
        """
        db = self._inv_repo.db
        expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.RESERVATION_TTL_MINUTES
        )

        # Phase 1: pre-flight check (no lock) — fast rejection before acquiring locks
        inventory_map: dict[int, Inventory] = {}
        for item in items:
            inv = await self._inv_repo.get_best_available(item["product_id"])
            if inv is None:
                raise InsufficientStockError(
                    f"Product {item['product_id']}: no inventory available"
                )
            effective = inv.qty_available - inv.qty_reserved
            if effective < item["qty"]:
                raise InsufficientStockError(
                    f"Product {item['product_id']}: requested {item['qty']}, "
                    f"available {effective}"
                )
            inventory_map[item["product_id"]] = inv

        # Phase 2: lock rows and re-check under lock
        locked_inventory: dict[int, Inventory] = {}
        for item in items:
            pre_inv = inventory_map[item["product_id"]]
            locked = await self._inv_repo.get_by_id_for_update(pre_inv.id)
            if locked is None:
                raise InsufficientStockError(
                    f"Product {item['product_id']}: inventory row disappeared"
                )
            effective = locked.qty_available - locked.qty_reserved
            if effective < item["qty"]:
                raise InsufficientStockError(
                    f"Product {item['product_id']}: requested {item['qty']}, "
                    f"available {effective} (re-checked under lock)"
                )
            locked_inventory[item["product_id"]] = locked

        # Phase 3: increment qty_reserved for all items
        for item in items:
            locked_inventory[item["product_id"]].qty_reserved += item["qty"]

        # Phase 4: persist reservation
        reservation = Reservation(
            user_id=user_id,
            status=ReservationStatus.pending,
            expires_at=expires_at,
        )
        db.add(reservation)
        await db.flush()

        # Phase 5: create items and call provider hold
        reservation_items: list[ReservationItem] = []
        for item in items:
            inv = locked_inventory[item["product_id"]]
            res_item = ReservationItem(
                reservation_id=reservation.id,
                product_id=item["product_id"],
                inventory_id=inv.id,
                provider_id=inv.provider_id,
                qty_requested=item["qty"],
                provider_status=ProviderItemStatus.pending,
            )
            db.add(res_item)
            await db.flush()

            adapter = self._registry.resolve(inv.provider, inv)
            try:
                hold_ref = await adapter.hold_stock(
                    sku=inv.product.sku,
                    qty=item["qty"],
                    reservation_id=reservation.id,
                )
                res_item.provider_hold_ref = hold_ref
                res_item.provider_status = ProviderItemStatus.held
            except InsufficientProviderStock as exc:
                # Provider has less stock than our DB reflects — roll back everything
                raise InsufficientStockError(
                    f"Product {item['product_id']}: provider rejected reservation: {exc}"
                ) from exc
            except (ProviderTimeout, ProviderUnavailable) as exc:
                # Fail-open: mark degraded, continue
                res_item.provider_status = ProviderItemStatus.provider_failed
                res_item.provider_error_message = str(exc)

            reservation_items.append(res_item)

        await db.flush()
        await db.refresh(reservation)
        return reservation

    async def get_with_items(self, reservation_id: int) -> Reservation:
        reservation = await self._res_repo.get_with_items(reservation_id)
        if reservation is None:
            raise ReservationNotFound(f"Reservation {reservation_id} not found")
        return reservation

    async def confirm(self, reservation_id: int) -> Order:
        """
        Consume inventory and create an order.
        - Provider confirm_hold is called for HELD items; failure is non-fatal.
        - Items with provider_failed skip the provider confirm call entirely.
        """
        db = self._inv_repo.db
        reservation = await self._res_repo.get_with_items(reservation_id)
        if reservation is None:
            raise ReservationNotFound(f"Reservation {reservation_id} not found")

        if reservation.status != ReservationStatus.pending:
            raise ReservationStateError(
                f"Cannot confirm reservation {reservation_id}: "
                f"status is '{reservation.status.value}'"
            )
        if reservation.expires_at < datetime.now(UTC):
            raise ReservationStateError(
                f"Cannot confirm reservation {reservation_id}: already expired"
            )

        existing_order = await self._order_repo.get_by_reservation_id(reservation_id)
        if existing_order is not None:
            raise DuplicateOrderError(
                f"Reservation {reservation_id} already has an order"
            )

        for item in reservation.items:
            locked_inv = await self._inv_repo.get_by_id_for_update(item.inventory_id)
            if locked_inv is not None:
                locked_inv.qty_available -= item.qty_requested
                locked_inv.qty_reserved -= item.qty_requested

            # Call provider confirm only for externally held items
            if (
                item.provider_status == ProviderItemStatus.held
                and item.provider_hold_ref is not None
            ):
                adapter = self._registry.resolve(item.provider)
                try:
                    await adapter.confirm_hold(item.provider_hold_ref)
                except (ProviderTimeout, ProviderUnavailable):
                    pass  # non-fatal: stock consumed locally; reconcile via sync

            item.provider_status = ProviderItemStatus.confirmed

        reservation.status = ReservationStatus.confirmed

        order = Order(
            reservation_id=reservation.id,
            user_id=reservation.user_id,
            status=OrderStatus.created,
        )
        db.add(order)
        await db.flush()
        await db.refresh(order)
        return order

    async def cancel(self, reservation_id: int) -> None:
        """
        Release held inventory. Idempotent: no-op if already cancelled or expired.
        """
        reservation = await self._res_repo.get_with_items(reservation_id)
        if reservation is None:
            raise ReservationNotFound(f"Reservation {reservation_id} not found")

        if reservation.status in (
            ReservationStatus.cancelled,
            ReservationStatus.expired,
        ):
            return  # idempotent

        if reservation.status != ReservationStatus.pending:
            raise ReservationStateError(
                f"Cannot cancel reservation {reservation_id}: "
                f"status is '{reservation.status.value}'"
            )

        await self._release_items(reservation)
        reservation.status = ReservationStatus.cancelled

    async def expire_batch(self, limit: int = 100) -> int:
        """
        Expire pending reservations past their TTL. Returns count expired.
        Uses SKIP LOCKED — safe to run concurrently across replicas.
        """
        expired = await self._res_repo.get_expired_pending(limit)
        for reservation in expired:
            await self._release_items(reservation)
            reservation.status = ReservationStatus.expired
        return len(expired)

    async def _release_items(self, reservation: Reservation) -> None:
        for item in reservation.items:
            if item.provider_status in (
                ProviderItemStatus.released,
                ProviderItemStatus.confirmed,
            ):
                continue

            locked_inv = await self._inv_repo.get_by_id_for_update(item.inventory_id)
            if locked_inv is not None:
                locked_inv.qty_reserved = max(
                    0, locked_inv.qty_reserved - item.qty_requested
                )

            if (
                item.provider_hold_ref is not None
                and item.provider_status == ProviderItemStatus.held
            ):
                adapter = self._registry.resolve(item.provider)
                try:
                    await adapter.release_hold(item.provider_hold_ref)
                except Exception:
                    pass  # release failure is non-fatal

            item.provider_status = ProviderItemStatus.released

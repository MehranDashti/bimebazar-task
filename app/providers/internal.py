from app.models.inventory import Inventory
from app.providers.base import BaseProviderAdapter, InsufficientProviderStock


class InternalProviderAdapter(BaseProviderAdapter):
    """
    Manages stock directly on the in-memory Inventory row.
    Caller holds a SELECT FOR UPDATE lock and commits the session.
    """

    def __init__(self, inventory_row: Inventory) -> None:
        self._row = inventory_row

    async def check_stock(self, sku: str) -> int:
        return self._row.qty_available - self._row.qty_reserved

    async def hold_stock(self, sku: str, qty: int, reservation_id: int) -> str | None:
        effective = self._row.qty_available - self._row.qty_reserved
        if effective < qty:
            raise InsufficientProviderStock(
                f"Internal: requested {qty}, available {effective}"
            )
        self._row.qty_reserved += qty
        return None  # internal holds don't issue external references

    async def release_hold(self, hold_ref: str) -> bool:
        return True  # caller decrements qty_reserved directly

    async def confirm_hold(self, hold_ref: str) -> bool:
        return True  # caller handles qty_available decrement

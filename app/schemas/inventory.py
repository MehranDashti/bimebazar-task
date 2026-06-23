from datetime import datetime

from pydantic import BaseModel


class InventoryAvailabilityItem(BaseModel):
    provider_id: int
    provider_name: str
    qty_available: int
    qty_reserved: int
    effective_available: int
    last_synced_at: datetime | None


class ProductAvailabilityResponse(BaseModel):
    product_id: int
    sources: list[InventoryAvailabilityItem]

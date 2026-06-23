from fastapi import APIRouter, Depends

from app.core.dependencies import get_inventory_service
from app.core.response import ok
from app.schemas.inventory import ProductAvailabilityResponse
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/{product_id}/availability", summary="Get effective available stock per provider")
async def get_availability(
    product_id: int,
    svc: InventoryService = Depends(get_inventory_service),
):
    data = await svc.get_availability(product_id)
    return ok(ProductAvailabilityResponse(**data))

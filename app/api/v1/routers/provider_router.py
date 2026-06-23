from fastapi import APIRouter, Depends

from app.core.dependencies import get_inventory_service
from app.core.response import ok
from app.schemas.provider import ProviderSyncResponse
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/providers", tags=["Providers"])


@router.post("/{provider_id}/sync", summary="Sync inventory from external provider")
async def sync_provider(
    provider_id: int,
    svc: InventoryService = Depends(get_inventory_service),
):
    result = await svc.sync_from_provider(provider_id)
    return ok(ProviderSyncResponse(**result))

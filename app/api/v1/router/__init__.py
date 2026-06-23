from fastapi import APIRouter

from app.api.v1.routers.auth_router import router as auth_router
from app.api.v1.routers.inventory_router import router as inventory_router
from app.api.v1.routers.order_router import router as order_router
from app.api.v1.routers.provider_router import router as provider_router
from app.api.v1.routers.reservation_router import router as reservation_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(reservation_router)
api_router.include_router(order_router)
api_router.include_router(inventory_router)
api_router.include_router(provider_router)

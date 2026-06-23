from fastapi import APIRouter, Depends

from app.core.dependencies import get_order_service, get_reservation_service
from app.core.response import ok
from app.schemas.order import OrderResponse, PaymentOutcomeRequest
from app.services.order_service import OrderService
from app.services.reservation_service import ReservationService

router = APIRouter(tags=["Orders"])


@router.post("/payment-outcome", summary="Process payment outcome event")
async def payment_outcome(
    body: PaymentOutcomeRequest,
    svc: ReservationService = Depends(get_reservation_service),
):
    if body.outcome == "success":
        order = await svc.confirm(body.reservation_id)
        return ok(OrderResponse.model_validate(order))
    else:
        await svc.cancel(body.reservation_id)
        return ok({"reservation_id": body.reservation_id, "status": "cancelled"})


@router.get("/orders/{order_id}", summary="Get order by ID")
async def get_order(
    order_id: int,
    order_svc: OrderService = Depends(get_order_service),
):
    order = await order_svc.get_by_id(order_id)
    return ok(OrderResponse.model_validate(order))

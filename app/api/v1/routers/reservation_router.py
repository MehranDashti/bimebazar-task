from fastapi import APIRouter, Depends

from app.core.dependencies import get_reservation_service
from app.core.response import created, no_content, ok
from app.schemas.reservation import ReservationCreateRequest, ReservationResponse
from app.services.reservation_service import ReservationService

router = APIRouter(prefix="/reservations", tags=["Reservations"])


@router.post("", summary="Create a reservation (initiate checkout)")
async def create_reservation(
    body: ReservationCreateRequest,
    svc: ReservationService = Depends(get_reservation_service),
):
    reservation = await svc.create(
        user_id=body.user_id,
        items=[{"product_id": i.product_id, "qty": i.qty} for i in body.items],
    )
    return created(ReservationResponse.from_reservation(reservation))


@router.get("/{reservation_id}", summary="Get reservation status and items")
async def get_reservation(
    reservation_id: int,
    svc: ReservationService = Depends(get_reservation_service),
):
    reservation = await svc.get_with_items(reservation_id)
    return ok(ReservationResponse.from_reservation(reservation))


@router.post("/{reservation_id}/confirm", summary="Confirm reservation after payment success")
async def confirm_reservation(
    reservation_id: int,
    svc: ReservationService = Depends(get_reservation_service),
):
    from app.schemas.order import OrderResponse
    order = await svc.confirm(reservation_id)
    return ok(OrderResponse.model_validate(order))


@router.post("/{reservation_id}/cancel", summary="Cancel reservation (abandon checkout)")
async def cancel_reservation(
    reservation_id: int,
    svc: ReservationService = Depends(get_reservation_service),
):
    await svc.cancel(reservation_id)
    return no_content()

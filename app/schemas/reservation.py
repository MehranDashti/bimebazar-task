from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

from app.models.reservation import ReservationStatus
from app.models.reservation_item import ProviderItemStatus

if TYPE_CHECKING:
    from app.models.reservation import Reservation
    from app.models.reservation_item import ReservationItem


class ReservationItemRequest(BaseModel):
    product_id: int = Field(gt=0)
    qty: int = Field(gt=0, le=1000)


class ReservationCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    items: list[ReservationItemRequest] = Field(min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def no_duplicate_products(
        cls, items: list[ReservationItemRequest]
    ) -> list[ReservationItemRequest]:
        pids = [i.product_id for i in items]
        if len(pids) != len(set(pids)):
            raise ValueError("Duplicate product_id in items list")
        return items


class ReservationItemResponse(BaseModel):
    id: int
    product_id: int
    provider_id: int
    provider_name: str = ""
    qty_requested: int
    provider_status: ProviderItemStatus
    provider_hold_ref: str | None
    provider_error_message: str | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_item(cls, item: ReservationItem) -> ReservationItemResponse:
        provider_name = ""
        if hasattr(item, "provider") and item.provider:
            provider_name = item.provider.name
        return cls(
            id=item.id,
            product_id=item.product_id,
            provider_id=item.provider_id, 
            provider_name=provider_name,
            qty_requested=item.qty_requested,
            provider_status=item.provider_status,
            provider_hold_ref=item.provider_hold_ref,
            provider_error_message=item.provider_error_message,
        )


class ReservationResponse(BaseModel):
    id: int
    user_id: str
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime
    items: list[ReservationItemResponse]

    model_config = {"from_attributes": True}

    @classmethod
    def from_reservation(cls, reservation: Reservation) -> ReservationResponse:
        items = [
            ReservationItemResponse.from_item(i)
            for i in (reservation.items or []) 
        ]
        return cls(
            id=reservation.id, 
            user_id=reservation.user_id,  
            status=reservation.status, 
            expires_at=reservation.expires_at, 
            created_at=reservation.created_at,  
            items=items,
        )

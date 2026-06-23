from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.order import OrderStatus


class PaymentOutcomeRequest(BaseModel):
    reservation_id: int = Field(gt=0)
    outcome: Literal["success", "failed"]


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    user_id: str
    status: OrderStatus
    created_at: datetime

    model_config = {"from_attributes": True}

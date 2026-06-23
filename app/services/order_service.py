from app.core.exceptions import NotFoundError
from app.models.order import Order
from app.repositories.order_repository import OrderRepository


class OrderService:
    def __init__(self, order_repo: OrderRepository) -> None:
        self._order_repo = order_repo

    async def get_by_id(self, order_id: int) -> Order:
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        return order

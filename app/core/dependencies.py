from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.reservation_repository import ReservationRepository
from app.repositories.user_repository import UserRepository
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
from app.services.reservation_service import ReservationService
from app.services.user_service import UserService
from app.providers.registry import ProviderRegistry

bearer_scheme = HTTPBearer(auto_error=False)


async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(user_repo=UserRepository(db))


async def get_reservation_service(
    db: AsyncSession = Depends(get_db),
) -> ReservationService:
    return ReservationService(
        inv_repo=InventoryRepository(db),
        res_repo=ReservationRepository(db),
        order_repo=OrderRepository(db),
        registry=ProviderRegistry(),
    )


async def get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
    return OrderService(order_repo=OrderRepository(db))


async def get_inventory_service(db: AsyncSession = Depends(get_db)) -> InventoryService:
    return InventoryService(inv_repo=InventoryRepository(db))


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub: str | None = payload.get("sub")
    token_type: str | None = payload.get("type")
    if sub is None or token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await UserRepository(db).get_by_id(int(sub))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials=credentials, db=db)
    except HTTPException:
        return None

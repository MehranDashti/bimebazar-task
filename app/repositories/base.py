from typing import TYPE_CHECKING, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Base

if TYPE_CHECKING:
    from app.db.pagination import PaginationParams

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    def __init__(self, model: type[T], db: AsyncSession) -> None:
        self.model = model
        self.db = db

    async def get_by_id(self, id: int) -> T | None:
        # Every model carries an int `id` PK, but the Base-bound TypeVar can't
        # express that to the type checker.
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)  # type: ignore[attr-defined]
        )
        return result.scalars().first()

    async def get_all(self) -> list[T]:
        result = await self.db.execute(select(self.model))
        return list(result.scalars().all())

    async def create(self, instance: T) -> T:
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def delete(self, instance: T) -> None:
        await self.db.delete(instance)
        await self.db.flush()

    async def _paginate(self, query: Select, pagination: "PaginationParams") -> tuple[list[T], int]:
        from app.db.pagination import paginate

        return await paginate(self.db, query, pagination)

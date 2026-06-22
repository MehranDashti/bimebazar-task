from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.example import Example
from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    from app.db.pagination import PaginationParams


class ExampleRepository(BaseRepository[Example]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Example, db)

    async def get_by_name(self, name: str) -> Example | None:
        result = await self.db.execute(select(Example).where(Example.name == name))
        return result.scalars().first()

    async def exists(self, name: str) -> bool:
        result = await self.db.execute(select(Example.id).where(Example.name == name))
        return result.scalars().first() is not None

    async def get_filtered_paginated(
        self,
        filters: dict[str, Any],
        sort_by: str | None,
        sort_order: str,
        pagination: "PaginationParams",
    ) -> tuple[list[Example], int]:
        from app.filters.example_filter import ExampleFilter

        f = ExampleFilter()
        query = f.apply(select(Example), filters)
        query = f.apply_sort(query, Example, sort_by, sort_order)
        return await self._paginate(query, pagination)

from typing import TYPE_CHECKING, Any

from app.core.exceptions import ConflictError
from app.models.example import Example
from app.repositories.example_repository import ExampleRepository
from app.services.base import BaseService

if TYPE_CHECKING:
    from app.db.pagination import PaginationParams


class ExampleService(BaseService[Example]):
    def __init__(self, repo: ExampleRepository) -> None:
        super().__init__(repo)
        self.repo: ExampleRepository

    async def create(self, name: str, description: str | None = None) -> Example:
        if await self.repo.exists(name):
            raise ConflictError(f"Example '{name}' already exists.")
        return await self.repo.create(Example(name=name, description=description))

    async def update(
        self,
        example_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> Example:
        example = await self.get_by_id(example_id)
        if name is not None:
            example.name = name
        if description is not None:
            example.description = description
        return await self._flush_refresh(example)

    async def get_paginated(
        self,
        filters: dict[str, Any],
        sort_by: str | None,
        sort_order: str,
        pagination: "PaginationParams",
    ) -> tuple[list[Example], int]:
        return await self.repo.get_filtered_paginated(filters, sort_by, sort_order, pagination)

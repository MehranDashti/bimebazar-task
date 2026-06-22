from typing import Generic, TypeVar

from app.core.exceptions import NotFoundError
from app.db.session import Base
from app.repositories.base import BaseRepository

T = TypeVar("T", bound=Base)


class BaseService(Generic[T]):
    def __init__(self, repo: BaseRepository[T]) -> None:
        self.repo = repo

    @property
    def _entity_name(self) -> str:
        return self.repo.model.__name__

    async def get_by_id(self, entity_id: int) -> T:
        entity = await self.repo.get_by_id(entity_id)
        if not entity:
            raise NotFoundError(f"{self._entity_name} with id {entity_id} not found.")
        return entity

    async def get_all(self) -> list[T]:
        return await self.repo.get_all()

    async def delete(self, entity_id: int) -> None:
        entity = await self.get_by_id(entity_id)
        await self.repo.delete(entity)

    async def _flush_refresh(self, entity: T) -> T:
        await self.repo.db.flush()
        await self.repo.db.refresh(entity)
        return entity

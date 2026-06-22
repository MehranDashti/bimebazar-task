from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession


class BaseCommand(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    async def handle(self, db: AsyncSession) -> None:
        """Command logic. db is already inside an open transaction."""
        ...

    async def run(self) -> None:
        """Bootstraps a DB session and calls handle()."""
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            async with db.begin():
                await self.handle(db)

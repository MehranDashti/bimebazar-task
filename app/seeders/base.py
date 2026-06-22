from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


class BaseSeeder(ABC):
    name: str
    description: str

    @abstractmethod
    async def run(self, db: AsyncSession) -> None: ...

    async def execute(self) -> None:
        import app.models  # noqa: F401

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            async with db.begin():
                await self.run(db)
        await engine.dispose()

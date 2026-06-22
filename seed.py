import asyncio

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings  # noqa: E402
from app.seeders.kernel import SEEDERS  # noqa: E402


async def run_all() -> None:
    import app.models  # noqa: F401

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        async with db.begin():
            for seeder_class in SEEDERS:
                seeder = seeder_class()
                print(f"\n→ {seeder.description}...")
                await seeder.run(db)
    await engine.dispose()
    print("\n✅ All seeders complete.")


if __name__ == "__main__":
    asyncio.run(run_all())

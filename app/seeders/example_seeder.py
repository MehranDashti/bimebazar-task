from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.example import Example

from .base import BaseSeeder


class ExampleSeeder(BaseSeeder):
    name = "examples"
    description = "Seed example records"

    async def run(self, db: AsyncSession) -> None:
        records = [
            ("Example One", "First seeded example"),
            ("Example Two", "Second seeded example"),
        ]
        for name, description in records:
            result = await db.execute(select(Example).where(Example.name == name))
            if not result.scalars().first():
                db.add(Example(name=name, description=description))
                await db.flush()
                print(f"   ✔ created  {name}")
            else:
                print(f"   — exists   {name}")

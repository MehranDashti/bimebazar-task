from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.base import BaseCommand


class ExampleCommand(BaseCommand):
    name = "example:run"
    description = "Template command — replace with real logic"

    async def handle(self, db: AsyncSession) -> None:
        # Use db for any ORM queries, e.g.:
        # from app.repositories.user_repository import UserRepository
        # repo = UserRepository(db)
        # users = await repo.get_all()
        print("→ ExampleCommand running...")
        print("✔ ExampleCommand done.")

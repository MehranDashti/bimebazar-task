from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalars().first()

    async def email_exists(self, email: str) -> bool:
        result = await self.db.execute(select(User.id).where(User.email == email))
        return result.scalars().first() is not None

    async def username_exists(self, username: str) -> bool:
        result = await self.db.execute(select(User.id).where(User.username == username))
        return result.scalars().first() is not None

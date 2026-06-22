from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    InactiveAccountError,
    NotFoundError,
)
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.base import BaseService


class UserService(BaseService[User]):
    def __init__(self, user_repo: UserRepository) -> None:
        super().__init__(user_repo)
        self.repo: UserRepository

    async def get_by_email(self, email: str) -> User:
        user = await self.repo.get_by_email(email)
        if not user:
            raise NotFoundError("User not found.")
        return user

    async def register(self, email: str, username: str, full_name: str, password: str) -> User:
        if await self.repo.email_exists(email):
            raise ConflictError("A user with this email already exists.")
        if await self.repo.username_exists(username):
            raise ConflictError("A user with this username already exists.")
        user = User(
            email=email,
            username=username,
            full_name=full_name,
            hashed_password=get_password_hash(password),
        )
        return await self.repo.create(user)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password.")
        if not user.is_active:
            raise InactiveAccountError("Account is inactive.")
        return user

    async def update_profile(
        self,
        user: User,
        full_name: str | None = None,
        password: str | None = None,
    ) -> User:
        if full_name is not None:
            user.full_name = full_name
        if password is not None:
            user.hashed_password = get_password_hash(password)
        return await self._flush_refresh(user)

    async def toggle_active(self, user_id: int) -> User:
        user = await self.get_by_id(user_id)
        user.is_active = not user.is_active
        return await self._flush_refresh(user)

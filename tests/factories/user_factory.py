import uuid

from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.user import User

_faker = Faker()


def user_payload(**overrides) -> dict:
    suffix = uuid.uuid4().hex[:8]
    return {
        "email": f"user_{suffix}@example.com",
        "username": f"user_{suffix}",
        "full_name": _faker.name(),
        "password": "Password1",
        **overrides,
    }


async def make_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    username: str | None = None,
    full_name: str | None = None,
    password: str = "Password1",
    is_active: bool = True,
) -> User:
    overrides: dict = {"password": password}
    if email is not None:
        overrides["email"] = email
    if username is not None:
        overrides["username"] = username
    if full_name is not None:
        overrides["full_name"] = full_name
    data = user_payload(**overrides)
    user = User(
        email=data["email"],
        username=data["username"],
        full_name=data["full_name"],
        hashed_password=get_password_hash(data["password"]),
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user

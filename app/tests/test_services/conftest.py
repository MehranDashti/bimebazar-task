import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tests.factories import make_example, make_user


@pytest.fixture
async def example(db_session: AsyncSession):
    return await make_example(db_session)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await make_user(db_session)

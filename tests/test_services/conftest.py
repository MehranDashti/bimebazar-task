import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_user


@pytest.fixture
async def user(db_session: AsyncSession):
    return await make_user(db_session)

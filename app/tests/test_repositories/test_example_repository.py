from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.example_repository import ExampleRepository
from app.tests.factories import make_example


async def test_get_by_name_found(db_session: AsyncSession):
    example = await make_example(db_session, name="findme")
    result = await ExampleRepository(db_session).get_by_name("findme")
    assert result is not None
    assert result.id == example.id


async def test_get_by_name_not_found(db_session: AsyncSession):
    assert await ExampleRepository(db_session).get_by_name("missing") is None


async def test_exists_true(db_session: AsyncSession):
    await make_example(db_session, name="exists")
    assert await ExampleRepository(db_session).exists("exists") is True


async def test_exists_false(db_session: AsyncSession):
    assert await ExampleRepository(db_session).exists("ghost") is False


async def test_create_and_get_by_id(db_session: AsyncSession):
    example = await make_example(db_session)
    result = await ExampleRepository(db_session).get_by_id(example.id)
    assert result is not None
    assert result.name == example.name


async def test_delete(db_session: AsyncSession):
    example = await make_example(db_session)
    repo = ExampleRepository(db_session)
    await repo.delete(example)
    assert await repo.get_by_id(example.id) is None

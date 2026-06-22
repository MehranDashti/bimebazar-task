import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.repositories.example_repository import ExampleRepository
from app.services.example_service import ExampleService
from app.tests.factories import make_example


def _svc(db: AsyncSession) -> ExampleService:
    return ExampleService(repo=ExampleRepository(db))


async def test_create_success(db_session: AsyncSession):
    example = await _svc(db_session).create(name="new-one", description="Hello")
    assert example.id is not None
    assert example.name == "new-one"
    assert example.description == "Hello"


async def test_create_conflict(db_session: AsyncSession):
    await make_example(db_session, name="dup")
    with pytest.raises(ConflictError):
        await _svc(db_session).create(name="dup")


async def test_get_by_id_found(db_session: AsyncSession):
    example = await make_example(db_session)
    result = await _svc(db_session).get_by_id(example.id)
    assert result.id == example.id


async def test_get_by_id_not_found(db_session: AsyncSession):
    with pytest.raises(NotFoundError):
        await _svc(db_session).get_by_id(9999)


async def test_update_name(db_session: AsyncSession):
    example = await make_example(db_session)
    updated = await _svc(db_session).update(example.id, name="renamed")
    assert updated.name == "renamed"


async def test_update_description(db_session: AsyncSession):
    example = await make_example(db_session)
    updated = await _svc(db_session).update(example.id, description="new desc")
    assert updated.description == "new desc"


async def test_delete(db_session: AsyncSession):
    example = await make_example(db_session)
    await _svc(db_session).delete(example.id)
    with pytest.raises(NotFoundError):
        await _svc(db_session).get_by_id(example.id)

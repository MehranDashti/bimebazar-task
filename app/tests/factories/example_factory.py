import uuid

from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.example import Example

_faker = Faker()


def example_payload(**overrides) -> dict:
    return {
        "name": f"example_{uuid.uuid4().hex[:8]}",
        "description": _faker.sentence(),
        **overrides,
    }


async def make_example(
    db: AsyncSession,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Example:
    overrides: dict = {}
    if name is not None:
        overrides["name"] = name
    if description is not None:
        overrides["description"] = description
    data = example_payload(**overrides)
    example = Example(name=data["name"], description=data.get("description"))
    db.add(example)
    await db.flush()
    await db.refresh(example)
    return example

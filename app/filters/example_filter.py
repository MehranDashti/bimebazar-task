from fastapi import Query

from app.filters.base import BaseFilter, FilterFn


class ExampleFilter(BaseFilter):
    def filters(self) -> dict[str, FilterFn]:
        from app.models.example import Example

        return {
            "name": lambda q, v: q.where(Example.name.ilike(f"%{v}%")),
        }

    def sortable_fields(self) -> set[str]:
        return {"id", "name", "created_at"}


class ExampleFilterParams:
    def __init__(
        self,
        name: str | None = Query(default=None, description="Partial name match"),
        sort_by: str | None = Query(default=None, description="Column to sort by"),
        sort_order: str = Query(default="asc", pattern="^(asc|desc)$", description="asc or desc"),
    ):
        self.name = name
        self.sort_by = sort_by
        self.sort_order = sort_order

    def to_dict(self) -> dict:
        return {"name": self.name}

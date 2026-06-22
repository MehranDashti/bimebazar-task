from collections.abc import Callable
from typing import Any

from sqlalchemy import Select, asc, desc

FilterFn = Callable[[Select, Any], Select]


class BaseFilter:
    """
    Subclass and override `filters()` to declare field-level filter callbacks.
    Mirrors the Osmose OsmoseFilter.residue() pattern for FastAPI/SQLAlchemy.

    Usage:
        f = UserFilter()
        query = f.apply(select(User), {"email": "alice", "is_active": True})
        query = f.apply_sort(query, User, sort_by="email", sort_order="asc")
    """

    def filters(self) -> dict[str, FilterFn]:
        """Map query-param name → callable(Select, value) -> Select."""
        return {}

    def sortable_fields(self) -> set[str]:
        """Whitelist of column names safe to ORDER BY."""
        return set()

    def apply(self, query: Select, params: dict[str, Any]) -> Select:
        """Apply all filters whose keys are present and non-None/non-empty in params."""
        for field, callback in self.filters().items():
            value = params.get(field)
            if value is not None and value != "":
                query = callback(query, value)
        return query

    def apply_sort(
        self,
        query: Select,
        model: Any,
        sort_by: str | None,
        sort_order: str,
    ) -> Select:
        """Apply ORDER BY. Falls back to created_at DESC when sort_by is absent or invalid."""
        if sort_by and sort_by in self.sortable_fields() and hasattr(model, sort_by):
            col = getattr(model, sort_by)
            return query.order_by(asc(col) if sort_order == "asc" else desc(col))
        if hasattr(model, "created_at"):
            return query.order_by(desc(model.created_at))
        return query

"""Modular filter registry for dashboard job table filtering.

Each filter is a self-contained definition with a key, label, and SQL WHERE
clause. Adding a new filter is one entry in DEFAULT_FILTERS — no route or
template changes needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Filter:
    """A single dashboard filter definition.

    Attributes:
        key: URL parameter value (e.g. 'hide_postulado').
        label: User-facing text in the filter menu.
        sql_where: SQL WHERE clause fragment when active, or None for
            custom client-side handling.
    """

    key: str
    label: str
    sql_where: str | None = None


@dataclass
class FilterRegistry:
    """Central registry of available filters.

    Provides lookup and WHERE-clause construction from a list of active
    filter keys.
    """

    filters: list[Filter] = field(default_factory=list)

    def register(self, filter_def: Filter) -> None:
        """Add a filter definition to the registry."""
        self.filters.append(filter_def)

    def by_key(self, key: str) -> Filter | None:
        """Look up a filter definition by its key."""
        return next((f for f in self.filters if f.key == key), None)

    def build_where_clauses(self, active_keys: list[str]) -> list[str]:
        """Build SQL WHERE clauses from a list of active filter keys.

        Only returns clauses for filters that have a sql_where defined.
        Unknown keys are silently ignored.
        """
        clauses: list[str] = []
        for key in active_keys:
            filter_def = self.by_key(key)
            if filter_def and filter_def.sql_where:
                clauses.append(filter_def.sql_where)
        return clauses


# -- Default filters ----------------------------------------------------------

DEFAULT_FILTERS = FilterRegistry(filters=[
    Filter(
        key="hide_postulado",
        label="Ocultar postulados",
        sql_where="status != 'postulado'",
    ),
    Filter(
        key="hide_errores",
        label="Ocultar errores",
        sql_where="status NOT IN ('general-error', 'auto-apply-failed-unavailable')",
    ),
    Filter(
        key="solo_pendientes",
        label="Solo pendientes",
        sql_where="(status = '' OR status IS NULL)",
    ),
])
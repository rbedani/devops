"""Unit tests for the dashboard filter registry."""

from src.dashboard.filters import DEFAULT_FILTERS, Filter, FilterRegistry


class TestFilter:
    """Filter dataclass — structural tests."""

    def test_filter_creation_with_sql(self):
        f = Filter(key="hide_test", label="Test filter", sql_where="status != 'x'")
        assert f.key == "hide_test"
        assert f.label == "Test filter"
        assert f.sql_where == "status != 'x'"

    def test_filter_creation_without_sql(self):
        f = Filter(key="custom", label="Custom")
        assert f.sql_where is None


class TestFilterRegistry:
    """FilterRegistry — registration, lookup, WHERE clause building."""

    def test_empty_registry_returns_no_clauses(self):
        reg = FilterRegistry()
        assert reg.build_where_clauses(["anything"]) == []

    def test_register_and_lookup(self):
        reg = FilterRegistry()
        f = Filter(key="hide_x", label="X", sql_where="x = 1")
        reg.register(f)
        assert reg.by_key("hide_x") is f
        assert reg.by_key("unknown") is None

    def test_build_where_clauses(self):
        reg = FilterRegistry(filters=[
            Filter("a", "A", "x = 1"),
            Filter("b", "B", "y = 2"),
        ])
        clauses = reg.build_where_clauses(["a", "b"])
        assert clauses == ["x = 1", "y = 2"]

    def test_build_with_unknown_keys_ignores_them(self):
        reg = FilterRegistry(filters=[
            Filter("a", "A", "x = 1"),
        ])
        clauses = reg.build_where_clauses(["a", "unknown"])
        assert clauses == ["x = 1"]

    def test_build_with_none_sql_key_skips_it(self):
        reg = FilterRegistry(filters=[
            Filter("a", "A", sql_where=None),
        ])
        assert reg.build_where_clauses(["a"]) == []

    def test_build_with_empty_active_keys(self):
        reg = FilterRegistry(filters=[
            Filter("a", "A", "x = 1"),
        ])
        assert reg.build_where_clauses([]) == []


class TestDefaultFilters:
    """DEFAULT_FILTERS — ensure the three expected filters exist."""

    def test_has_hide_postulado(self):
        f = DEFAULT_FILTERS.by_key("hide_postulado")
        assert f is not None
        assert f.label == "Ocultar postulados"
        assert "postulado" in (f.sql_where or "")

    def test_has_hide_errores(self):
        f = DEFAULT_FILTERS.by_key("hide_errores")
        assert f is not None
        assert f.label == "Ocultar errores"
        assert "general-error" in (f.sql_where or "")

    def test_has_solo_pendientes(self):
        f = DEFAULT_FILTERS.by_key("solo_pendientes")
        assert f is not None
        assert f.label == "Solo pendientes"
        assert "status" in (f.sql_where or "")

    def test_all_defaults_have_sql(self):
        for f in DEFAULT_FILTERS.filters:
            assert f.sql_where is not None, f"Filter '{f.key}' has no sql_where"

    def test_build_all_defaults(self):
        clauses = DEFAULT_FILTERS.build_where_clauses([
            "hide_postulado", "hide_errores", "solo_pendientes",
        ])
        assert len(clauses) == 3

    def test_combined_clause_contains_all_status_references(self):
        clauses = DEFAULT_FILTERS.build_where_clauses([
            "hide_postulado", "hide_errores", "solo_pendientes",
        ])
        combined = " AND ".join(clauses)
        assert "postulado" in combined
        assert "general-error" in combined
        assert "auto-apply-failed-unavailable" in combined
        assert "status" in combined
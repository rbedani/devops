"""Unit tests for date-range filtering (parser + matches_date_range).

Formats under test come from real jobs.db data: ISO 8601, DD/MM/YYYY,
"Hace Nd/Nh/Nm" relative text, and "D mon" Spanish abbreviations.
"""

from datetime import UTC, datetime, timedelta

from src.core.config.search import SearchFilters, _parse_fecha_publicacion

# Fixed reference "now" so relative parsing is deterministic.
NOW = datetime(2026, 8, 1, 12, 0)


class TestParseFechaPublicacion:
    """_parse_fecha_publicacion — mixed formats → naive UTC datetime or None."""

    def test_iso_datetime(self):
        parsed = _parse_fecha_publicacion("2026-07-24T10:30:00", now=NOW)
        assert parsed == datetime(2026, 7, 24, 10, 30)

    def test_iso_with_z_suffix(self):
        parsed = _parse_fecha_publicacion("2026-07-24T10:30:00Z", now=NOW)
        assert parsed == datetime(2026, 7, 24, 10, 30)

    def test_iso_date_only(self):
        parsed = _parse_fecha_publicacion("2026-07-24", now=NOW)
        assert parsed == datetime(2026, 7, 24)

    def test_iso_with_offset_converted_to_utc(self):
        parsed = _parse_fecha_publicacion("2026-07-24T10:30:00+02:00", now=NOW)
        assert parsed == datetime(2026, 7, 24, 8, 30)

    def test_dd_slash_mm_yyyy(self):
        parsed = _parse_fecha_publicacion("24/07/2026", now=NOW)
        assert parsed == datetime(2026, 7, 24)

    def test_dd_dash_mm_yyyy(self):
        parsed = _parse_fecha_publicacion("24-07-2026", now=NOW)
        assert parsed == datetime(2026, 7, 24)

    def test_hace_2d(self):
        parsed = _parse_fecha_publicacion("Hace 2d", now=NOW)
        assert parsed == NOW - timedelta(days=2)

    def test_hace_5h(self):
        parsed = _parse_fecha_publicacion("Hace 5h", now=NOW)
        assert parsed == NOW - timedelta(hours=5)

    def test_hace_30m(self):
        parsed = _parse_fecha_publicacion("Hace 30m", now=NOW)
        assert parsed == NOW - timedelta(minutes=30)

    def test_short_relative_2d(self):
        parsed = _parse_fecha_publicacion("2d", now=NOW)
        assert parsed == NOW - timedelta(days=2)

    def test_d_mon_current_year(self):
        parsed = _parse_fecha_publicacion("5 jul", now=NOW)
        assert parsed == datetime(2026, 7, 5)

    def test_d_mon_future_infers_previous_year(self):
        parsed = _parse_fecha_publicacion("5 dic", now=NOW)
        assert parsed == datetime(2025, 12, 5)

    def test_invalid_numeric_date_returns_none(self):
        assert _parse_fecha_publicacion("31/02/2026", now=NOW) is None

    def test_empty_string_returns_none(self):
        assert _parse_fecha_publicacion("", now=NOW) is None

    def test_garbage_returns_none(self):
        assert _parse_fecha_publicacion("garbage", now=NOW) is None


def _job(fecha: str | None):
    """Fake job with a fixed fecha_publicacion tag (pattern from test_search)."""
    return type(
        "Job",
        (),
        {"get_tag": lambda self, k: fecha if k == "fecha_publicacion" else None},
    )()


class TestMatchesDateRange:
    """matches_date_range — conservative semantics: missing data always passes."""

    def test_empty_range_passes_all(self):
        f = SearchFilters(date_range="")
        assert f.matches_date_range(_job("Hace 1d"))

    def test_unknown_range_passes_all(self):
        f = SearchFilters(date_range="raro")
        assert f.matches_date_range(_job("Hace 1d"))

    def test_missing_tag_passes(self):
        f = SearchFilters(date_range="last_24h")
        assert f.matches_date_range(_job(None))

    def test_unparseable_tag_passes(self):
        f = SearchFilters(date_range="last_24h")
        assert f.matches_date_range(_job("garbage"))

    def test_last_24h_hace_1d_passes_inclusive_boundary(self):
        f = SearchFilters(date_range="last_24h")
        assert f.matches_date_range(_job("Hace 1d"))

    def test_last_24h_hace_2d_fails(self):
        f = SearchFilters(date_range="last_24h")
        assert not f.matches_date_range(_job("Hace 2d"))

    def test_last_week_hace_7d_passes_inclusive_boundary(self):
        f = SearchFilters(date_range="last_week")
        assert f.matches_date_range(_job("Hace 7d"))

    def test_last_month_hace_30d_passes_inclusive_boundary(self):
        f = SearchFilters(date_range="last_month")
        assert f.matches_date_range(_job("Hace 30d"))

    def test_iso_within_cutoff(self):
        iso = (datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=5)).isoformat()
        f = SearchFilters(date_range="last_24h")
        assert f.matches_date_range(_job(iso))

    def test_iso_outside_cutoff(self):
        iso = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)).isoformat()
        f = SearchFilters(date_range="last_24h")
        assert not f.matches_date_range(_job(iso))

    def test_dd_mm_yyyy_respects_cutoff(self):
        past = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
        assert not SearchFilters(date_range="last_24h").matches_date_range(
            _job(past.strftime("%d/%m/%Y"))
        )
        assert SearchFilters(date_range="last_week").matches_date_range(
            _job(past.strftime("%d/%m/%Y"))
        )

    def test_custom_range_inclusive(self):
        f = SearchFilters(date_range="2026-07-01:2026-07-15")
        assert f.matches_date_range(_job("2026-07-15T00:00:00"))
        assert f.matches_date_range(_job("2026-07-01T00:00:00"))

    def test_custom_range_outside_fails(self):
        f = SearchFilters(date_range="2026-07-01:2026-07-10")
        assert not f.matches_date_range(_job("2026-07-15T00:00:00"))

    def test_custom_range_unparseable_bound_passes(self):
        f = SearchFilters(date_range="basura:2026-07-15")
        assert f.matches_date_range(_job("2026-07-01T00:00:00"))

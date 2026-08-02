"""Unit tests for salary filter (src/core/config/search.py).

RED protocol (Strict TDD): written FIRST, references production code that
does not exist yet — `_parse_salary` and `SearchFilters.matches_salary`.

Covers:
- _parse_salary (D1): k-suffix, plain number, thousand-dots, €-suffix,
  full range with "b/a", single value and range → (min, max) tuple;
  no numbers → None
- matches_salary (D2/D3): min-only, max-only, both bounds, empty filters,
  inverted range, missing tag, unparseable tag, inclusive boundaries

Canonical salary tag key is "salario" (job.salary property); the DB
migration renamed 'salary' → 'salario' (src/core/db/database.py).
"""

from __future__ import annotations

from src.core.config.search import SearchFilters, _parse_salary
from src.core.models.job import Job


def _job_with_salary(raw: str | None) -> Job:
    """Build a minimal Job whose 'salario' tag holds the given raw text."""
    job = Job(source="test", title="DevOps", url="https://example.com/1")
    if raw is not None:
        job.set_tag("salario", raw, 1.0)
    return job


class TestParseSalary:
    """D1 — raw salary text → (min, max) tuple of euros per year."""

    def test_k_suffix_single_value(self) -> None:
        """RED: '30k' is a single value → (30000, 30000)."""
        assert _parse_salary("30k") == (30000, 30000)

    def test_plain_number_single_value(self) -> None:
        """TRIANGULATE: '30000' is a single value → (30000, 30000)."""
        assert _parse_salary("30000") == (30000, 30000)

    def test_thousand_dots_single_value(self) -> None:
        """TRIANGULATE: '30.000' (ES thousands dots) → (30000, 30000)."""
        assert _parse_salary("30.000") == (30000, 30000)

    def test_euro_suffix_single_value(self) -> None:
        """TRIANGULATE: '30000€' strips the € suffix → (30000, 30000)."""
        assert _parse_salary("30000€") == (30000, 30000)

    def test_full_range_with_b_a(self) -> None:
        """RED: '€36.000 - €42.000 b/a' → (36000, 42000) inclusive."""
        assert _parse_salary("€36.000 - €42.000 b/a") == (36000, 42000)

    def test_k_suffix_range(self) -> None:
        """TRIANGULATE: '30k - 40k' → (30000, 40000)."""
        assert _parse_salary("30k - 40k") == (30000, 40000)

    def test_range_without_symbols(self) -> None:
        """TRIANGULATE: '36.000 - 42.000' → (36000, 42000)."""
        assert _parse_salary("36.000 - 42.000") == (36000, 42000)

    def test_no_numbers_returns_none(self) -> None:
        """RED: 'No especificado' has no numbers → None."""
        assert _parse_salary("No especificado") is None

    def test_empty_string_returns_none(self) -> None:
        """TRIANGULATE: '' has no numbers → None."""
        assert _parse_salary("") is None

    def test_salary_by_hour_is_still_parsed_as_first_value(self) -> None:
        """EDGE: '15€/hora' parses to a single value, no crash."""
        assert _parse_salary("15€/hora") == (15, 15)


class TestMatchesSalary:
    """D2/D3 — salary filter matrix over job.get_tag('salario')."""

    def _filters(self, salary_min: str = "", salary_max: str = "") -> SearchFilters:
        return SearchFilters(salary_min=salary_min, salary_max=salary_max)

    def test_empty_filters_match_anything(self) -> None:
        """RED: no salary bounds → every job passes."""
        assert self._filters().matches_salary(_job_with_salary("36.000 - 42.000 b/a"))

    def test_min_only_job_range_above_min_passes(self) -> None:
        """RED: min=30000, job 36k-42k → passes (job_max >= min)."""
        assert self._filters(salary_min="30000").matches_salary(
            _job_with_salary("€36.000 - €42.000 b/a")
        )

    def test_min_only_job_below_min_fails(self) -> None:
        """TRIANGULATE: min=30000, job 25k → fails (job_max < min)."""
        assert not self._filters(salary_min="30000").matches_salary(_job_with_salary("25k"))

    def test_max_only_job_range_below_max_passes(self) -> None:
        """RED: max=40000, job 36k-42k → passes (job_min <= max)."""
        assert self._filters(salary_max="40000").matches_salary(
            _job_with_salary("€36.000 - €42.000 b/a")
        )

    def test_max_only_job_above_max_fails(self) -> None:
        """TRIANGULATE: max=40000, job 45k-50k → fails (job_min > max)."""
        assert not self._filters(salary_max="40000").matches_salary(
            _job_with_salary("45.000 - 50.000")
        )

    def test_both_bounds_overlapping_range_passes(self) -> None:
        """RED: 30k-45k vs job 36k-42k → passes (overlap)."""
        assert self._filters(salary_min="30000", salary_max="45000").matches_salary(
            _job_with_salary("€36.000 - €42.000 b/a")
        )

    def test_both_bounds_job_fully_above_fails(self) -> None:
        """TRIANGULATE: 30k-35k vs job 36k-42k → fails (no overlap)."""
        assert not self._filters(salary_min="30000", salary_max="35000").matches_salary(
            _job_with_salary("€36.000 - €42.000 b/a")
        )

    def test_inverted_bounds_ignored_both(self) -> None:
        """RED (D5): min>max → backend ignores BOTH bounds (job always passes)."""
        assert self._filters(salary_min="50000", salary_max="30000").matches_salary(
            _job_with_salary("36.000 - 42.000 b/a")
        )

    def test_inverted_bounds_single_value_also_passes(self) -> None:
        """TRIANGULATE (D5): inverted bounds never filter, even vs low salary."""
        assert self._filters(salary_min="50000", salary_max="30000").matches_salary(
            _job_with_salary("25k")
        )

    def test_missing_tag_passes(self) -> None:
        """RED: job without salario tag → passes (conservative)."""
        assert self._filters(salary_min="30000").matches_salary(_job_with_salary(None))

    def test_unparseable_tag_passes(self) -> None:
        """RED: unparseable salary text → passes (conservative)."""
        assert self._filters(salary_min="30000").matches_salary(
            _job_with_salary("Competitive")
        )

    def test_unparseable_min_filter_passes(self) -> None:
        """RED: unparseable FILTER min (e.g. 'Competitive') → bound ignored.

        Regression: _parse_salary('Competitive') is None and the old code
        crashed with TypeError (None[0]). The filter bound must be treated
        like the job side: unparseable = no restriction.
        """
        assert self._filters(salary_min="Competitive").matches_salary(
            _job_with_salary("36.000 - 42.000 b/a")
        )

    def test_unparseable_max_filter_passes(self) -> None:
        """RED: unparseable FILTER max → bound ignored, no crash."""
        assert self._filters(salary_max="Competitive").matches_salary(
            _job_with_salary("36.000 - 42.000 b/a")
        )

    def test_unparseable_both_filters_pass(self) -> None:
        """TRIANGULATE: both filter bounds unparseable → passes, no crash."""
        assert self._filters(
            salary_min="Competitive", salary_max="Negotiable"
        ).matches_salary(_job_with_salary("36.000 - 42.000 b/a"))

    def test_unparseable_min_does_not_filter_low_job(self) -> None:
        """TRIANGULATE: unparseable min must NOT act as zero/negative bound.

        A low job (20k) with an unparseable min filter must still pass —
        the bound is ignored, not treated as 0.
        """
        assert self._filters(salary_min="Competitive").matches_salary(
            _job_with_salary("20k")
        )

    def test_min_boundary_inclusive(self) -> None:
        """TRIANGULATE (D2): job at exactly min → passes (inclusive)."""
        assert self._filters(salary_min="30000").matches_salary(_job_with_salary("30k"))

    def test_max_boundary_inclusive(self) -> None:
        """TRIANGULATE (D2): job at exactly max → passes (inclusive)."""
        assert self._filters(salary_max="30000").matches_salary(_job_with_salary("30k"))

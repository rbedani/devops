"""Unit tests for SCAN keyword UI override helpers (src/scan/overrides.py).

Covers:
- split_keywords (SCAN-KW-03): comma split, whitespace strip, empty parts dropped
- matches_any_keyword (SCAN-KW-04): any-match title/company, case-insensitive
- apply_env_overrides (SCAN-KW-01/02/06): presence overrides, empty clears,
  coexists with location/modality, unknown keys ignored
"""

from __future__ import annotations

from src.core.config.search import SearchFilters, SearchTarget
from src.core.models.job import Job


def _job(title: str, company: str = "") -> Job:
    """Build a minimal Job for keyword filter tests."""
    return Job(source="test", title=title, url=f"https://example.com/{title}", company=company)


class TestSplitKeywords:
    """SCAN-KW-03 — raw UI keyword input → cleaned keyword list."""

    def test_empty_string_returns_no_keywords(self) -> None:
        """RED: "" should produce no keywords (no filter)."""
        from src.scan.overrides import split_keywords

        assert split_keywords("") == []

    def test_single_keyword(self) -> None:
        """RED: "devops" should produce a single keyword."""
        from src.scan.overrides import split_keywords

        assert split_keywords("devops") == ["devops"]

    def test_double_comma_drops_empty_parts(self) -> None:
        """TRIANGULATE: "devops,,sre" should produce two keywords, no empties."""
        from src.scan.overrides import split_keywords

        assert split_keywords("devops,,sre") == ["devops", "sre"]

    def test_strips_whitespace_around_keywords(self) -> None:
        """TRIANGULATE: " devops ,  sre " should be stripped to clean keywords."""
        from src.scan.overrides import split_keywords

        assert split_keywords(" devops ,  sre ") == ["devops", "sre"]

    def test_preserves_accents(self) -> None:
        """TRIANGULATE: accents survive the split (sanitize keeps them)."""
        from src.scan.overrides import split_keywords

        assert split_keywords("administración, devops") == ["administración", "devops"]

    def test_empty_keywords_still_build_params_without_crashing(self) -> None:
        """EDGE: cleared keywords ([]) must not crash to_*_params builders."""
        from src.scan.overrides import split_keywords

        filters = SearchFilters(keywords=split_keywords(""))
        assert filters.to_linkedin_params() == {}
        assert filters.to_infojobs_params() == {}
        assert filters.to_indeed_params() == {}
        assert filters.to_tecnoempleo_params() == {}


class TestMatchesAnyKeyword:
    """SCAN-KW-04 — post-scrape keyword filter (any-match, case-insensitive)."""

    def test_matches_title(self) -> None:
        """RED: keyword in job title should match."""
        from src.scan.overrides import matches_any_keyword

        assert matches_any_keyword(_job("DevOps Engineer", "Acme"), ["devops"])

    def test_matches_company(self) -> None:
        """TRIANGULATE: keyword in company name should match."""
        from src.scan.overrides import matches_any_keyword

        assert matches_any_keyword(_job("Platform Engineer", "SRE Corp"), ["sre"])

    def test_case_insensitive(self) -> None:
        """TRIANGULATE: case differences should not matter."""
        from src.scan.overrides import matches_any_keyword

        assert matches_any_keyword(_job("DevOps Engineer", "Acme"), ["DEVOPS"])

    def test_any_match_across_keywords(self) -> None:
        """TRIANGULATE: any of several keywords should match."""
        from src.scan.overrides import matches_any_keyword

        assert matches_any_keyword(_job("Cloud Architect", "Acme"), ["devops", "cloud"])

    def test_no_match_returns_false(self) -> None:
        """RED: no keyword in title or company should return False."""
        from src.scan.overrides import matches_any_keyword

        assert not matches_any_keyword(_job("Backend Engineer", "Acme"), ["devops"])

    def test_empty_keyword_list_matches_everything(self) -> None:
        """EDGE: no keywords = no keyword filter (legacy behavior)."""
        from src.scan.overrides import matches_any_keyword

        assert matches_any_keyword(_job("Backend Engineer", "Acme"), [])


class TestApplyEnvOverrides:
    """SCAN-KW-01/02/06 — presence-based env overrides applied to target filters."""

    def test_presence_overrides_configured_keywords(self) -> None:
        """RED (SCAN-KW-01): "keywords" presence overrides filters.keywords."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin", filters=SearchFilters(keywords=["devops"])
        )
        apply_env_overrides(target, {"keywords": "sre, platform"})
        assert target.filters.keywords == ["sre", "platform"]

    def test_empty_keyword_clears_filter(self) -> None:
        """RED (SCAN-KW-02): empty keyword value clears keywords (no filter)."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin", filters=SearchFilters(keywords=["devops"])
        )
        apply_env_overrides(target, {"keywords": ""})
        assert target.filters.keywords == []

    def test_coexists_with_location_and_modality(self) -> None:
        """TRIANGULATE (SCAN-KW-06): keyword override coexists with location/modality."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin",
            filters=SearchFilters(keywords=["devops"], countries=["España"], modalities=["remote"]),
        )
        apply_env_overrides(
            target, {"keywords": "devops", "location": "Spain, Argentina", "modality": "hybrid"}
        )
        assert target.filters.keywords == ["devops"]
        assert target.filters.countries == ["Spain", "Argentina"]
        assert target.filters.modalities == ["hybrid"]

    def test_date_range_override_and_clear(self) -> None:
        """TRIANGULATE: date_range presence overrides; empty clears (Any time)."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin", filters=SearchFilters(date_range="last_month")
        )
        apply_env_overrides(target, {"date_range": "last_week"})
        assert target.filters.date_range == "last_week"
        apply_env_overrides(target, {"date_range": ""})
        assert target.filters.date_range == ""

    def test_empty_modality_clears_filter(self) -> None:
        """TRIANGULATE: empty modality = explicit no filter."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin", filters=SearchFilters(modalities=["remote"])
        )
        apply_env_overrides(target, {"modality": ""})
        assert target.filters.modalities == []

    def test_unknown_keys_ignored(self) -> None:
        """EDGE: unknown keys should not raise nor clobber other overrides."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin", filters=SearchFilters(keywords=["devops"])
        )
        apply_env_overrides(target, {"keywords": "sre", "bogus_key": "x"})
        assert target.filters.keywords == ["sre"]

    def test_no_overrides_leaves_filters_untouched(self) -> None:
        """EDGE: empty overrides dict = legacy config behavior."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin",
            filters=SearchFilters(keywords=["devops"], date_range="last_week"),
        )
        apply_env_overrides(target, {})
        assert target.filters.keywords == ["devops"]
        assert target.filters.date_range == "last_week"


class TestApplySalaryOverrides:
    """SCAN-SAL-01/02 — salary_min/salary_max presence-based env overrides.

    Mirrors the keyword override contract: presence overrides the configured
    filter, empty string = explicit "no filter". The raw values are kept
    as-is — run_search.py / _parse_salary normalise them later (D4: the
    parser is the single normaliser).
    """

    def test_salary_min_presence_overrides_configured_value(self) -> None:
        """RED: "salary_min" presence overrides filters.salary_min."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin",
            filters=SearchFilters(salary_min="20000", salary_max="50000"),
        )
        apply_env_overrides(target, {"salary_min": "30000"})
        assert target.filters.salary_min == "30000"

    def test_salary_max_presence_overrides_configured_value(self) -> None:
        """RED: "salary_max" presence overrides filters.salary_max."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin",
            filters=SearchFilters(salary_min="20000", salary_max="50000"),
        )
        apply_env_overrides(target, {"salary_max": "60000"})
        assert target.filters.salary_max == "60000"

    def test_empty_salary_min_clears_filter(self) -> None:
        """RED: empty salary_min = explicit no filter ("")."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin",
            filters=SearchFilters(salary_min="20000", salary_max="50000"),
        )
        apply_env_overrides(target, {"salary_min": ""})
        assert target.filters.salary_min == ""

    def test_empty_salary_max_clears_filter(self) -> None:
        """TRIANGULATE: empty salary_max = explicit no filter ("")."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin",
            filters=SearchFilters(salary_min="20000", salary_max="50000"),
        )
        apply_env_overrides(target, {"salary_max": ""})
        assert target.filters.salary_max == ""

    def test_salary_overrides_coexist_with_keywords(self) -> None:
        """TRIANGULATE: salary overrides coexist with keyword override."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin",
            filters=SearchFilters(keywords=["devops"], salary_min="20000"),
        )
        apply_env_overrides(target, {"keywords": "sre", "salary_min": "30000"})
        assert target.filters.keywords == ["sre"]
        assert target.filters.salary_min == "30000"

    def test_salary_keys_absent_leave_filters_untouched(self) -> None:
        """EDGE: absent salary keys do not touch configured filters."""
        from src.scan.overrides import apply_env_overrides

        target = SearchTarget(
            name="t", platform="linkedin",
            filters=SearchFilters(salary_min="20000", salary_max="50000"),
        )
        apply_env_overrides(target, {"keywords": "sre"})
        assert target.filters.salary_min == "20000"
        assert target.filters.salary_max == "50000"

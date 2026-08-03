"""Unit tests for SCAN keyword UI override helpers (src/scan/overrides.py).

Covers:
- split_keywords (SCAN-KW-03): comma split, whitespace strip, empty parts dropped
- matches_any_keyword (SCAN-KW-04): any-match title/company/description,
  case-insensitive, token-aware (delegates to src/scan/matcher.py)
- apply_env_overrides (SCAN-KW-01/02/06): presence overrides, empty clears,
  coexists with location/modality, unknown keys ignored
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.core.config.search import SearchFilters, SearchTarget
from src.core.models.job import Job

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_POST_FILTER_DRIVER = PROJECT_ROOT / "tests" / "unit" / "_main_post_filter_driver.py"
PER_KEYWORD_DRIVER = PROJECT_ROOT / "tests" / "unit" / "_per_keyword_driver.py"


def _run_per_keyword_driver(
    tmp_path: Path, *, mode: str = "main", **env: str
) -> tuple[dict, str]:
    """Run the per-keyword subprocess driver and return (report dict, stdout)."""
    report = tmp_path / "report.json"
    driver_env = os.environ.copy()
    driver_env.update(
        {
            "DB_PATH": str(tmp_path / "jobs.db"),
            "REPORT_PATH": str(report),
            "DRIVER_MODE": mode,
            **env,
        }
    )
    proc = subprocess.run(
        [sys.executable, str(PER_KEYWORD_DRIVER)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=PROJECT_ROOT,
        env=driver_env,
    )
    assert proc.returncode == 0, f"driver failed: {proc.stderr[-2000:]}"
    return json.loads(report.read_text(encoding="utf-8")), proc.stdout


def _job(title: str, company: str = "", description: str = "") -> Job:
    """Build a minimal Job for keyword filter tests."""
    return Job(
        source="test",
        title=title,
        url=f"https://example.com/{title}",
        company=company,
        description=description,
    )


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
    """SCAN-KW-04 — post-scrape keyword filter (any-match, case-insensitive).

    Delegates to the token-aware relevance matcher (src/scan/matcher.py):
    matching now spans title + company + description per spec
    (job-relevance-matcher), with synonyms and contiguous-phrase rules.
    """

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

    def test_matches_description_only(self) -> None:
        """RED (spec 'Keyword only in description'): desc-only match passes.

        Contract change: the SCAN keyword gate now spans title + company +
        description via the relevance matcher, so a job whose keyword appears
        only in the enriched description must pass.
        """
        from src.scan.overrides import matches_any_keyword

        assert matches_any_keyword(
            _job("Platform Engineer", "Acme", "We need terraform for our infra"),
            ["terraform"],
        )

    def test_empty_description_with_no_match_is_filtered(self) -> None:
        """TRIANGULATE (spec 'Empty description'): empty desc + no t/c match -> out."""
        from src.scan.overrides import matches_any_keyword

        assert not matches_any_keyword(
            _job("Backend Engineer", "Acme", ""),
            ["terraform"],
        )

    def test_synonym_matches_through_delegation(self) -> None:
        """TRIANGULATE (spec 'Synonym match passes'): k8s matches 'kubernetes'."""
        from src.scan.overrides import matches_any_keyword

        assert matches_any_keyword(
            _job("Platform Engineer", "Acme", "k8s administration"),
            ["kubernetes"],
        )


class TestMainPostFilter:
    """D4 — main() SCAN_KEYWORD post-filter must use the new relevance matcher.

    Runs scripts.run_search.main() in a subprocess (the module swaps
    sys.stdout at import time, so in-process import breaks pytest capture).
    The driver patches run_target to return a description-only match and
    deliberately breaks the legacy matcher: if main() still routed the
    post-filter through matches_any_keyword, the job would be dropped and
    its title would never appear in the output table.
    """

    def test_desc_only_job_survives_post_filter(self, tmp_path: Path) -> None:
        """RED (D4 CRITICAL): desc-only job keeps after SCAN_KEYWORD filter."""
        env = os.environ.copy()
        env["DB_PATH"] = str(tmp_path / "jobs.db")
        env["SCAN_KEYWORD"] = "terraform"

        proc = subprocess.run(
            [sys.executable, str(MAIN_POST_FILTER_DRIVER)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=PROJECT_ROOT,
            env=env,
        )
        assert proc.returncode == 0, f"driver failed: {proc.stderr[-2000:]}"
        assert "Platform SRE Engineer" in proc.stdout, (
            "description-only job was dropped by the SCAN_KEYWORD post-filter; "
            "main() must use the new relevance matcher (D4)"
        )


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


class TestApplyKeywordHelper:
    """D1 — `_apply_keyword(base_params, keyword)` pure helper (scripts/run_search.py).

    Copies base_params and overrides the platform keyword key with ONE keyword:
    "keywords" for LinkedIn, "keyword" for InfoJobs/Tecnoempleo/Indeed-compat
    (run_target already patches Indeed's "q" to "keyword"). Every other param
    is preserved; the input dict is never mutated.
    """

    def test_linkedin_keyword_key_override(self, tmp_path: Path) -> None:
        """RED: LinkedIn base uses "keywords" → overridden to the single keyword."""
        report, _ = _run_per_keyword_driver(tmp_path, mode="helpers")
        assert report["apply_linkedin"] == {
            "keywords": "devops",
            "location": "Spain",
            "f_TPR": "r86400",
        }

    def test_infojobs_keyword_key_override(self, tmp_path: Path) -> None:
        """TRIANGULATE: InfoJobs/Tecnoempleo base uses "keyword" → overridden."""
        report, _ = _run_per_keyword_driver(tmp_path, mode="helpers")
        assert report["apply_infojobs"] == {"keyword": "sre", "city": "Madrid"}

    def test_no_keyword_key_returns_plain_copy(self, tmp_path: Path) -> None:
        """TRIANGULATE: base without a keyword key stays unchanged (no query filter)."""
        report, _ = _run_per_keyword_driver(tmp_path, mode="helpers")
        assert report["apply_no_key"] == {"location": "Spain"}

    def test_none_keyword_returns_unchanged_copy(self, tmp_path: Path) -> None:
        """TRIANGULATE: unconstrained pass (kw None) must not add/alter keys."""
        report, _ = _run_per_keyword_driver(tmp_path, mode="helpers")
        assert report["apply_none"] == {"keywords": "devops sre"}

    def test_base_params_never_mutated(self, tmp_path: Path) -> None:
        """EDGE: helper copies — the caller's base_params must stay intact."""
        report, _ = _run_per_keyword_driver(tmp_path, mode="helpers")
        assert report["apply_copy"]["out"] == {"keywords": "sre", "location": "Spain"}
        assert report["apply_copy"]["base_after"] == {"keywords": "devops sre", "location": "Spain"}


class TestKeywordPassesHelper:
    """D1 — `_keyword_passes(keywords)` dedup helper (scripts/run_search.py).

    Duplicate keywords collapse preserving order; an empty list becomes one
    unconstrained pass ([None]); multi-word phrases stay whole.
    """

    def test_duplicate_keywords_collapse_preserving_order(self, tmp_path: Path) -> None:
        """RED (spec 'Duplicate keywords collapse'): ["devops","devops","sre"] → 2 passes."""
        report, _ = _run_per_keyword_driver(tmp_path, mode="helpers")
        assert report["passes_dedup"] == ["devops", "sre"]

    def test_empty_list_means_single_unconstrained_pass(self, tmp_path: Path) -> None:
        """RED (spec 'No keywords'): [] → [None] = one unconstrained pass."""
        report, _ = _run_per_keyword_driver(tmp_path, mode="helpers")
        assert report["passes_empty"] == [None]

    def test_phrase_keyword_stays_whole(self, tmp_path: Path) -> None:
        """TRIANGULATE (spec 'Literal phrase'): "data engineer" is one pass, not two."""
        report, _ = _run_per_keyword_driver(tmp_path, mode="helpers")
        assert report["passes_phrase"] == ["data engineer", "devops"]


class TestPerKeywordLoop:
    """D1/D3 — per-keyword OR loop inside _scrape_and_enrich (scripts/run_search.py).

    Runs main() in a subprocess with a fake scraper recording every
    scrape_search call: one query per keyword (deduped), outer keyword ×
    inner location, shared seen_urls across keyword passes, per-keyword log.
    """

    def test_two_keywords_produce_two_queries(self, tmp_path: Path) -> None:
        """RED (spec 'Two keywords produce two queries'): devops + sre → 2 queries."""
        report, _ = _run_per_keyword_driver(
            tmp_path, TARGET_KEYWORDS="devops,sre"
        )
        assert [c["query"] for c in report["calls"]] == ["devops", "sre"]

    def test_duplicate_keywords_issue_one_query(self, tmp_path: Path) -> None:
        """RED (spec 'Duplicate keywords collapse'): devops,devops,sre → 2 queries."""
        report, _ = _run_per_keyword_driver(
            tmp_path, TARGET_KEYWORDS="devops,devops,sre"
        )
        assert [c["query"] for c in report["calls"]] == ["devops", "sre"]

    def test_no_keywords_single_unconstrained_pass(self, tmp_path: Path) -> None:
        """RED (spec 'No keywords'): empty list → one query without keyword."""
        report, _ = _run_per_keyword_driver(tmp_path, TARGET_KEYWORDS="")
        assert len(report["calls"]) == 1
        assert report["calls"][0]["query"] == ""

    def test_keyword_times_location_cross_product(self, tmp_path: Path) -> None:
        """RED (D1 outer kw × inner location): 2 kw × 2 loc → 4 ordered passes."""
        report, _ = _run_per_keyword_driver(
            tmp_path, TARGET_KEYWORDS="devops,sre", TARGET_LOCATIONS="Spain,Madrid"
        )
        assert [c["query"] for c in report["calls"]] == [
            "devops", "devops", "sre", "sre",
        ]
        assert [c["location"] for c in report["calls"]] == [
            "Spain", "Madrid", "Spain", "Madrid",
        ]

    def test_multiword_phrase_stays_whole_in_query(self, tmp_path: Path) -> None:
        """RED (spec 'Multi-word phrase stays whole'): query is the literal phrase."""
        report, _ = _run_per_keyword_driver(
            tmp_path, TARGET_KEYWORDS="data engineer,devops"
        )
        assert [c["query"] for c in report["calls"]] == ["data engineer", "devops"]

    def test_shared_urls_deduped_across_keywords(self, tmp_path: Path) -> None:
        """RED (spec merge+dedup): same URL set for both keywords → 5 unique, not 10."""
        report, _ = _run_per_keyword_driver(
            tmp_path, TARGET_KEYWORDS="devops,sre", SHARED_URLS="1"
        )
        assert report["total_unique"] == 5

    def test_native_filters_applied_to_every_keyword(self, tmp_path: Path) -> None:
        """RED (spec 'Native filter parameters ... unchanged'): f_TPR on every call."""
        report, _ = _run_per_keyword_driver(
            tmp_path, TARGET_KEYWORDS="devops,sre", TARGET_DATE_RANGE="last_24h"
        )
        assert len(report["calls"]) == 2
        for call in report["calls"]:
            assert call["extra_params"] == {"f_TPR": "r86400"}

    def test_per_keyword_log_lines(self, tmp_path: Path) -> None:
        """RED (spec 'Per-keyword counts logged'): per-kw unique count in the log."""
        _, stdout = _run_per_keyword_driver(tmp_path, TARGET_KEYWORDS="devops,sre")
        assert "Keyword 'devops': 5 unique jobs found" in stdout
        assert "Keyword 'sre': 5 unique jobs found" in stdout

    def test_shared_urls_log_zero_for_second_keyword(self, tmp_path: Path) -> None:
        """TRIANGULATE: cross-keyword dedup → second keyword contributes 0 new."""
        _, stdout = _run_per_keyword_driver(
            tmp_path, TARGET_KEYWORDS="devops,sre", SHARED_URLS="1"
        )
        assert "Keyword 'devops': 5 unique jobs found" in stdout
        assert "Keyword 'sre': 0 unique jobs found" in stdout

    def test_infojobs_per_platform_keyword_key(self, tmp_path: Path) -> None:
        """TRIANGULATE: InfoJobs "keyword" key path drives per-keyword queries."""
        report, _ = _run_per_keyword_driver(
            tmp_path, TARGET_PLATFORM="infojobs", TARGET_KEYWORDS="devops,sre"
        )
        assert [c["query"] for c in report["calls"]] == ["devops", "sre"]


class TestDebugCap:
    """D2 — PER_KEYWORD_DEBUG_CAP semantics (scripts/run_search.py).

    Debug mode caps results per keyword at 3; production is uncapped;
    targets.json max_results is dormant (kept, not enforced); the global
    max_jobs stop still applies in debug.
    """

    def test_debug_caps_three_per_keyword(self, tmp_path: Path) -> None:
        """RED (spec 'Debug caps per keyword'): 2 kw × 5 offers → ≤6 unique."""
        report, _ = _run_per_keyword_driver(
            tmp_path, TARGET_KEYWORDS="devops,sre", DEBUG_MODE="99"
        )
        assert report["total_unique"] == 6
        for call in report["calls"]:
            assert call["max_results"] == 3

    def test_production_uncapped(self, tmp_path: Path) -> None:
        """RED (spec 'Production collects all'): no DEBUG_MODE → all 10 collected."""
        report, _ = _run_per_keyword_driver(tmp_path, TARGET_KEYWORDS="devops,sre")
        assert report["total_unique"] == 10
        for call in report["calls"]:
            assert call["max_results"] is None

    def test_targets_max_results_dormant(self, tmp_path: Path) -> None:
        """RED (D2): targets.json max_results=25 must NOT be enforced."""
        report, _ = _run_per_keyword_driver(
            tmp_path,
            TARGET_KEYWORDS="devops,sre",
            TARGET_MAX_RESULTS="25",
            DEBUG_MODE="99",
        )
        assert report["total_unique"] == 6  # 3/kw cap wins over max_results=25
        for call in report["calls"]:
            assert call["max_results"] == 3

    def test_global_max_jobs_stop_coexists(self, tmp_path: Path) -> None:
        """TRIANGULATE (D2): DEBUG_MODE=3 global stop still truncates to 3 total."""
        report, _ = _run_per_keyword_driver(
            tmp_path, TARGET_KEYWORDS="devops,sre", DEBUG_MODE="3"
        )
        assert report["total_unique"] == 3

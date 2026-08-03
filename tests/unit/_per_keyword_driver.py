"""Subprocess driver for per-keyword loop + debug-cap tests (D1/D2/D3).

scripts.run_search swaps sys.stdout at import time (TextIOWrapper), so it
cannot be imported inside a pytest process without breaking capture — it is
executed here in a fresh interpreter instead (precedent: _main_post_filter_driver.py).

Two modes (env DRIVER_MODE):
- helpers: exercise the pure helpers `_apply_keyword` / `_keyword_passes` and
  dump their outputs for assertion (no main() run).
- main: patch load_targets + the scraper classes with env-driven fakes, run
  main(), and dump the recorded scrape_search calls plus the final unique
  job count (captured by patching format_jobs_table).

Target shape is env-driven:
  TARGET_PLATFORM      (linkedin|infojobs)
  TARGET_KEYWORDS      (comma-separated list)
  TARGET_LOCATIONS     (comma-separated list)
  TARGET_MAX_RESULTS   (int; feeds targets.json-style max_results dormancy checks)
  TARGET_DATE_RANGE    (e.g. last_24h → native f_TPR filter)
  DEBUG_MODE           (optional; per-keyword debug cap path)
  SHARED_URLS=1        → every query returns the SAME URL set (cross-keyword dedup)
  WALK_BLOCK_QUERY     (D6) query that simulates a mid-walk block: it returns
                       only WALK_BLOCK_COUNT partial results (the cards
                       collected before the block), proving the scan keeps
                       partials and continues with the next keyword
  WALK_BLOCK_COUNT     (default 2) partial results returned for the blocked query
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.run_search as rs  # noqa: E402
from src.core.config.search import SearchFilters, SearchTarget  # noqa: E402
from src.core.models.job import Job  # noqa: E402

OFFERS_PER_QUERY = 5


def build_fake_scraper(shared: bool) -> tuple[type, list[dict]]:
    """Return a FakeScraper class + the list where it records scrape_search calls."""

    calls: list[dict] = []

    # D6 — WALK_BLOCK_QUERY simulates a mid-walk block for one keyword: that
    # query returns only WALK_BLOCK_COUNT partial results (cards collected
    # before the block). The scan must keep them and continue with the next
    # keyword instead of crashing or dropping the partials.
    walk_block_query = os.environ.get("WALK_BLOCK_QUERY", "")
    walk_block_count = int(os.environ.get("WALK_BLOCK_COUNT", "2"))

    class FakeScraper:
        def __init__(self, db, headless: bool = True) -> None:  # noqa: ANN001
            pass

        async def __aenter__(self) -> FakeScraper:
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def scrape_search(
            self,
            query: str = "",
            location: str = "",
            max_results: int | None = None,
            extra_params: dict | None = None,
        ) -> list[Job]:
            calls.append(
                {
                    "query": query,
                    "location": location,
                    "max_results": max_results,
                    "extra_params": extra_params,
                }
            )
            if walk_block_query and query == walk_block_query:
                count = walk_block_count
            elif max_results is None:
                count = OFFERS_PER_QUERY
            else:
                count = min(max_results, OFFERS_PER_QUERY)
            stem = "shared" if shared else (query or "any")
            return [
                Job(
                    source="fake",
                    title=f"{query or 'any'} #{i}",
                    url=f"https://fake/{stem}/{location or 'any'}/{i}",
                    company="Acme",
                    location=location,
                )
                for i in range(count)
            ]

        async def scrape_detail(self, url: str) -> Job:
            return Job(source="fake", title="detail", url=url)

        def auto_detect_tags(self, job: Job) -> Job:
            return job

        def save_job(self, job: Job) -> int:
            return 0

    return FakeScraper, calls


def run_helpers(report_path: Path) -> None:
    """Mode 'helpers' — dump pure-helper outputs for in-process assertion."""

    base = {"keywords": "devops sre", "location": "Spain"}
    report = {
        "apply_linkedin": rs._apply_keyword(
            {"keywords": "devops sre", "location": "Spain", "f_TPR": "r86400"}, "devops"
        ),
        "apply_infojobs": rs._apply_keyword({"keyword": "devops sre", "city": "Madrid"}, "sre"),
        "apply_no_key": rs._apply_keyword({"location": "Spain"}, "devops"),
        "apply_none": rs._apply_keyword({"keywords": "devops sre"}, None),
        "apply_copy": {"out": rs._apply_keyword(base, "sre"), "base_after": base},
        "passes_dedup": rs._keyword_passes(["devops", "devops", "sre"]),
        "passes_empty": rs._keyword_passes([]),
        "passes_phrase": rs._keyword_passes(["data engineer", "devops"]),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def run_main(report_path: Path) -> None:
    """Mode 'main' — run rs.main() with a fake scraper and dump observable state."""

    platform = os.environ.get("TARGET_PLATFORM", "linkedin")
    keywords = [k for k in os.environ.get("TARGET_KEYWORDS", "").split(",") if k]
    locations = [loc for loc in os.environ.get("TARGET_LOCATIONS", "").split(",") if loc]
    max_results = int(os.environ.get("TARGET_MAX_RESULTS", "25"))
    date_range = os.environ.get("TARGET_DATE_RANGE", "")
    shared = os.environ.get("SHARED_URLS") == "1"

    fake_scraper_cls, calls = build_fake_scraper(shared)

    def fake_load_targets(path: Path) -> list[SearchTarget]:
        filters = SearchFilters(keywords=keywords, countries=locations, date_range=date_range)
        return [
            SearchTarget(
                name="fake", platform=platform, filters=filters, max_results=max_results
            )
        ]

    # Module-level monkeypatches: mypy cannot see through these test harness
    # swaps, so each assignment carries a targeted ignore (repo precedent:
    # _main_post_filter_driver.py).
    rs.load_targets = fake_load_targets  # type: ignore[assignment]
    rs.LinkedInScraper = fake_scraper_cls  # type: ignore[assignment, misc]
    rs.InfoJobsScraper = fake_scraper_cls  # type: ignore[assignment, misc]
    rs.IndeedScraper = fake_scraper_cls  # type: ignore[assignment, misc]
    rs.TecnoempleoScraper = fake_scraper_cls  # type: ignore[assignment, misc]

    final_count: dict[str, int] = {}

    def fake_format_jobs_table(jobs: list, title: str = "") -> str:
        final_count["n"] = len(jobs)
        return ""

    rs.format_jobs_table = fake_format_jobs_table

    asyncio.run(rs.main())

    report = {
        "calls": calls,
        "total_unique": final_count.get("n", -1),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    report_path = Path(os.environ["REPORT_PATH"])
    if os.environ.get("DRIVER_MODE", "main") == "helpers":
        run_helpers(report_path)
    else:
        run_main(report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run job search using configured targets."""

import asyncio
import io
import json
import logging
import os
import sys

from src.core.config.settings import TARGETS_PATH, DB_PATH
from src.core.config.search import SearchTarget, load_targets
from src.scan.matcher import matches_relevance
from src.scan.overrides import apply_env_overrides, split_keywords
from src.scrapers.linkedin import LinkedInScraper
from src.scrapers.infojobs import InfoJobsScraper
from src.scrapers.indeed import IndeedScraper
from src.scrapers.tecnoempleo import TecnoempleoScraper

from src.core.db.database import JobDatabase, run_migrations
from src.alerts.telegram import format_jobs_table

# Force UTF-8 everywhere on Windows — prevents garbled characters like españa
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

CONFIG_PATH = TARGETS_PATH


def _keyword_passes(keywords: list[str]) -> list[str | None]:
    """Deduplicate keywords preserving first-seen order (spec: duplicate collapse).

    An empty keyword list becomes a single unconstrained pass ([None]),
    preserving the legacy no-keyword behavior (spec: keyword-search-iteration
    "No keywords").
    """
    if not keywords:
        return [None]
    return list(dict.fromkeys(keywords))


def _apply_keyword(base_params: dict, keyword: str | None) -> dict:
    """Copy base params, overriding the platform keyword key with ONE keyword.

    LinkedIn uses "keywords"; InfoJobs/Tecnoempleo/Indeed-compat use
    "keyword" (run_target already patches Indeed's "q" to "keyword").
    keyword=None (unconstrained pass) or a base without a keyword key
    returns a plain copy. The input dict is never mutated.
    """
    params = dict(base_params)
    if keyword is None:
        return params
    if "keywords" in params:
        params["keywords"] = keyword
    elif "keyword" in params:
        params["keyword"] = keyword
    return params


async def _scrape_and_enrich(
    scraper,
    target: SearchTarget,
    locations: list[str],
    base_params: dict[str, str],
    extra_params: dict[str, str],
    max_jobs: int | None,
    emit_progress,
) -> list:
    """Shared search + dedup + enrich logic for all platforms.

    Issues one platform query per keyword (OR semantics, D1): an outer
    keyword × inner location loop that deduplicates by URL across ALL
    passes via the shared seen_urls set. Native filter parameters
    (extra_params) are applied to every keyword query unchanged. Each
    job is enriched with its detail page, post-scrape filters applied,
    and saved.
    """
    all_jobs: list = []
    seen_urls: set[str] = set()
    total_locations = len(locations)

    # D1 — outer keyword × inner location. Duplicate keywords collapse and
    # an empty keyword list yields one unconstrained pass (spec: per-keyword
    # query iteration).
    keyword_passes = _keyword_passes(target.filters.keywords)
    total_passes = len(keyword_passes) * total_locations
    pass_count = 0
    search_done = False

    for keyword in keyword_passes:
        kw_label = keyword if keyword else "(no keyword)"
        kw_params = _apply_keyword(base_params, keyword)
        kw_new_count = 0
        for loc_idx, location in enumerate(locations):
            loc_label = location if location else "(any)"
            pass_count += 1
            logger.info("  Searching location %d/%d: %s", loc_idx + 1, total_locations, loc_label)

            jobs = await scraper.scrape_search(
                query=kw_params.get("keywords", kw_params.get("keyword", "")),
                location=location,
                max_results=target.max_results if max_jobs is not None else None,
                extra_params=extra_params,
            )

            # Deduplicate by URL across keywords AND locations (shared seen_urls)
            new_count = 0
            for job in jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)
                    new_count += 1
            kw_new_count += new_count
            logger.info("  Location '%s': %d jobs (%d new, %d total unique)",
                        loc_label, len(jobs), new_count, len(all_jobs))

            # Search phase progress — distribute 20% across kw × loc passes
            emit_progress((pass_count / total_passes) * 20)

            # Apply global limit when set (debug mode: stop after N total)
            if max_jobs is not None and len(all_jobs) >= max_jobs:
                all_jobs = all_jobs[:max_jobs]
                search_done = True
                break

        # Per-keyword unique-URL count (spec: per-keyword result logging)
        logger.info("  Keyword '%s': %d unique jobs found", kw_label, kw_new_count)
        if search_done:
            break

    # Search phase done — 20% of target allocation
    emit_progress(20)

    # Enrich each job with detail page (80% of target allocation)
    enriched = []
    total_jobs = len(all_jobs)
    for i, job in enumerate(all_jobs):
        try:
            detail = await scraper.scrape_detail(job.url)
            if detail.description:
                job.description = detail.description
            # Merge structured data from detail page into the card-level job
            if detail.location and not job.location:
                job.location = detail.location
            if detail.company and not job.company:
                job.company = detail.company
            # Merge tags from detail (modality, salary) — don't overwrite with "no disponible"
            for tag_key in ("modalidad", "salary"):
                detail_val = detail.get_tag(tag_key)
                if detail_val and "no disponible" not in detail_val.lower():
                    if not job.get_tag(tag_key):
                        job.set_tag(tag_key, detail_val, 0.9)
            job = scraper.auto_detect_tags(job)
        except Exception as e:
            logger.warning("Failed to enrich '%s': %s", job.title, e)

        # Apply post-scrape modalidad + date-range + salary filter
        if (
            target.filters.matches_job(job)
            and target.filters.matches_date_range(job)
            and target.filters.matches_salary(job)
        ):
            scraper.save_job(job)
            enriched.append(job)

        # Emit progress after each enrichment
        enrich_pct = 20 + ((i + 1) / total_jobs) * 80 if total_jobs else 100
        emit_progress(enrich_pct)

        # Stop early when global limit is reached
        if max_jobs is not None and len(enriched) >= max_jobs:
            break

    return enriched


async def run_target(
    target: SearchTarget,
    db: JobDatabase,
    target_index: int = 0,
    total_targets: int = 1,
    max_jobs: int | None = None,
    env_overrides: dict[str, str] | None = None,
) -> list:
    """Execute a single search target and return jobs found.

    Emits PROGRESS lines for intra-target granularity so the progress bar
    animates smoothly even with a single target. Progress allocation per target:
      20% after search phase, 80% split across job detail enrichment.

    When max_jobs is set, stops early once that many jobs are enriched,
    used in debug mode to stop the scan after 3 total results.

    When env_overrides is provided, the target's filters are overridden
    before building LinkedIn search params (used for SCAN_DATE_RANGE,
    SCAN_LOCATION, SCAN_MODALITY overrides from the dashboard UI).
    """
    base_pct = (target_index / total_targets) * 100

    def emit_progress(inner_pct: float) -> None:
        overall = round(base_pct + inner_pct * (100 / total_targets) / 100, 1)
        print(f"PROGRESS:{target.name}:{overall}%", flush=True)

    # Apply env var overrides to target filters BEFORE logging/building params
    # (keywords, date_range, location, modality — presence-based; empty = no filter)
    if env_overrides:
        apply_env_overrides(target, env_overrides)

    # Resolve locations list (already split if from override, or from config)
    locations = [loc.strip() for loc in target.filters.countries if loc.strip()]
    if not locations:
        locations = [""]  # One empty-location pass = no geo filter

    logger.info("Running target: %s", target.name)
    logger.info("  Platform: %s", target.platform)
    logger.info("  Keywords: %s", target.filters.keywords)
    logger.info("  Countries: %s", target.filters.countries)
    logger.info("  Modalities: %s", target.filters.modalities)
    logger.info("  Date: %s", target.filters.date_range)
    logger.info("  Locations to search: %d (%s)", len(locations), locations)

    if target.platform == "linkedin":
        async with LinkedInScraper(db=db, headless=True) as scraper:
            base_params = target.filters.to_linkedin_params()
            extra_params = {
                k: v
                for k, v in base_params.items()
                if k not in ("keywords", "location")
            }
            enriched = await _scrape_and_enrich(
                scraper, target, locations, base_params, extra_params,
                max_jobs, emit_progress,
            )
            logger.info("Target '%s': %d jobs passed filters (searched %d locations)",
                        target.name, len(enriched), len(locations))
            return enriched
    elif target.platform == "infojobs":
        async with InfoJobsScraper(db=db, headless=True) as scraper:
            base_params = target.filters.to_infojobs_params()
            extra_params = {
                k: v
                for k, v in base_params.items()
                if k not in ("keyword", "city")
            }
            enriched = await _scrape_and_enrich(
                scraper, target, locations, base_params, extra_params,
                max_jobs, emit_progress,
            )
            logger.info("Target '%s': %d jobs passed filters (searched %d locations)",
                        target.name, len(enriched), len(locations))
            return enriched
    elif target.platform == "indeed":
        async with IndeedScraper(db=db, headless=True) as scraper:
            base_params = target.filters.to_indeed_params()
            # Indeed uses "q" for keywords, not "keywords"/"keyword"
            indeed_query = base_params.get("q", "")
            extra_params = {
                k: v
                for k, v in base_params.items()
                if k not in ("q", "l")
            }
            # Patch _scrape_and_enrich to use "q" for query
            # We create a copy with "keyword" set for _scrape_and_enrich compatibility
            compat_params = dict(base_params)
            compat_params["keyword"] = indeed_query
            enriched = await _scrape_and_enrich(
                scraper, target, locations, compat_params, extra_params,
                max_jobs, emit_progress,
            )
            logger.info("Target '%s': %d jobs passed filters (searched %d locations)",
                        target.name, len(enriched), len(locations))
            return enriched
    elif target.platform == "tecnoempleo":
        async with TecnoempleoScraper(db=db, headless=True) as scraper:
            base_params = target.filters.to_tecnoempleo_params()
            extra_params = {
                k: v
                for k, v in base_params.items()
                if k not in ("keyword",)
            }
            enriched = await _scrape_and_enrich(
                scraper, target, locations, base_params, extra_params,
                max_jobs, emit_progress,
            )
            logger.info("Target '%s': %d jobs passed filters (searched %d locations)",
                        target.name, len(enriched), len(locations))
            return enriched
    else:
        logger.error("Unsupported platform: %s (supported: linkedin, infojobs, indeed, tecnoempleo)", target.platform)
        return []


async def main():
    # Load targets
    if not CONFIG_PATH.exists():
        logger.error("Config not found: %s", CONFIG_PATH)
        sys.exit(1)

    targets = load_targets(CONFIG_PATH)
    enabled = [t for t in targets if t.enabled]

    # Filter by SCRAPE_PLATFORM env var when set
    scan_platform = os.environ.get("SCRAPE_PLATFORM", "").strip()
    if scan_platform:
        enabled = [t for t in enabled if t.platform.lower() == scan_platform.lower()]

    logger.info("Loaded %d targets (%d enabled)", len(targets), len(enabled))

    db = JobDatabase(DB_PATH)
    run_migrations(DB_PATH)
    all_jobs = []
    total = len(enabled)
    completed = 0

    # Debug mode: stop scan completely after N total results
    debug_mode = os.environ.get("DEBUG_MODE")
    if debug_mode:
        try:
            debug_limit = int(debug_mode)
        except (ValueError, TypeError):
            debug_limit = None
    else:
        debug_limit = None

    # Build env var overrides for dashboard SCAN parameters.
    # These override the target's config filters when the dashboard
    # user changes search params on the fly (date_range, location, modality).
    env_overrides: dict[str, str] = {}

    # Date range — always check presence, not truthiness.
    # Empty string means "user chose Any time" (no date filter).
    if "SCAN_DATE_RANGE" in os.environ:
        scan_date_range = os.environ["SCAN_DATE_RANGE"].strip()
        env_overrides["date_range"] = scan_date_range  # may be empty
        if scan_date_range:
            logger.info("SCAN_DATE_RANGE override: %s", scan_date_range)
        else:
            logger.info("SCAN_DATE_RANGE override: cleared (Any time — no date filter)")

    # Location — always check presence, not truthiness.
    # Empty string means "user explicitly cleared the location" (override config default).
    if "SCAN_LOCATION" in os.environ:
        scan_location = os.environ["SCAN_LOCATION"].strip()
        env_overrides["location"] = scan_location  # may be empty
        if scan_location:
            logger.info("SCAN_LOCATION override: %s", scan_location)
        else:
            logger.info("SCAN_LOCATION override: cleared (no location filter)")

    # Modality — always check presence, not just truthiness.
    # Empty string means "user explicitly chose no filter" (override config default).
    if "SCAN_MODALITY" in os.environ:
        scan_modality = os.environ["SCAN_MODALITY"].strip()
        env_overrides["modality"] = scan_modality  # may be empty
        if scan_modality:
            logger.info("SCAN_MODALITY override: %s", scan_modality)
        else:
            logger.info("SCAN_MODALITY override: cleared (no modality filter)")

    # Keywords — always check presence, not truthiness.
    # Empty string means "user cleared keywords" (override config default).
    # The raw value keeps commas/accents (sanitized earlier in runner.py);
    # the split into a keyword list happens in apply_env_overrides.
    if "SCAN_KEYWORD" in os.environ:
        scan_keywords = os.environ["SCAN_KEYWORD"].strip()
        env_overrides["keywords"] = scan_keywords  # may be empty
        if scan_keywords:
            logger.info("SCAN_KEYWORD override: %s", scan_keywords)
        else:
            logger.info("SCAN_KEYWORD override: cleared (no keyword filter)")

    # Salary — always check presence, not truthiness.
    # Empty string means "user cleared the salary filter" (override config
    # default). Raw values travel untouched; the parser in search.py is the
    # single normaliser. Inverted bounds (min > max) are handled by
    # matches_salary, which ignores both (UI shows the warning instead).
    if "SCAN_SALARY_MIN" in os.environ:
        scan_salary_min = os.environ["SCAN_SALARY_MIN"].strip()
        env_overrides["salary_min"] = scan_salary_min  # may be empty
        if scan_salary_min:
            logger.info("SCAN_SALARY_MIN override: %s", scan_salary_min)
        else:
            logger.info("SCAN_SALARY_MIN override: cleared (no min salary filter)")

    if "SCAN_SALARY_MAX" in os.environ:
        scan_salary_max = os.environ["SCAN_SALARY_MAX"].strip()
        env_overrides["salary_max"] = scan_salary_max  # may be empty
        if scan_salary_max:
            logger.info("SCAN_SALARY_MAX override: %s", scan_salary_max)
        else:
            logger.info("SCAN_SALARY_MAX override: cleared (no max salary filter)")

    for i, target in enumerate(enabled):
        remaining = None
        if debug_limit is not None:
            remaining = debug_limit - len(all_jobs)
            if remaining <= 0:
                logger.info("Debug mode: reached %d jobs, stopping scan", debug_limit)
                break

        jobs = await run_target(
            target, db,
            target_index=i, total_targets=total,
            max_jobs=remaining,
            env_overrides=env_overrides if env_overrides else None,
        )
        all_jobs.extend(jobs)
        completed += 1

    # Post-scrape keyword filter (from SCAN_KEYWORD env var).
    # Presence-based: when the var is absent, no filter is applied (legacy
    # behavior — SCAN-KW-07). When present, the effective keyword list is
    # split from the raw value and any-match filtered on title, company and
    # description via the token-aware relevance matcher (D4 — must not use
    # the legacy title/company gate or description-only matches are lost).
    if "SCAN_KEYWORD" in os.environ:
        effective_keywords = split_keywords(os.environ["SCAN_KEYWORD"])
        before = len(all_jobs)
        all_jobs = [
            job for job in all_jobs
            if matches_relevance(job, effective_keywords)
        ]
        after = len(all_jobs)
        logger.info("SCAN_KEYWORD filter %s: %d → %d jobs", effective_keywords, before, after)

    # Summary
    print(f"\n{'=' * 70}")
    print(f"  TOTAL: {len(all_jobs)} jobs across {len(enabled)} targets")
    print(f"  DB: {db.count()} jobs total")
    print(f"{'=' * 70}")

    # Print formatted results
    if all_jobs:
        print("\n" + format_jobs_table(all_jobs, title="📋 Ofertas DevOps — España (última semana)"))

    db.close()


if __name__ == "__main__":
    asyncio.run(main())

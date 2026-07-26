#!/usr/bin/env python3
"""Run job search using configured targets."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from src.config.search import SearchTarget, load_targets
from src.scrapers.linkedin import LinkedInScraper
from src.db.database import JobDatabase
from src.alerts.telegram import format_jobs_table

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config/targets.json")
DB_PATH = "jobs.db"


async def run_target(target: SearchTarget, db: JobDatabase, target_index: int = 0, total_targets: int = 1, max_jobs: int | None = None) -> list:
    """Execute a single search target and return jobs found.

    Emits PROGRESS lines for intra-target granularity so the progress bar
    animates smoothly even with a single target. Progress allocation per target:
      20% after search phase, 80% split across job detail enrichment.

    When max_jobs is set, stops early once that many jobs are enriched,
    used in debug mode to stop the scan after 3 total results.
    """
    base_pct = (target_index / total_targets) * 100

    def emit_progress(inner_pct: float) -> None:
        overall = round(base_pct + inner_pct * (100 / total_targets) / 100, 1)
        print(f"PROGRESS:{target.name}:{overall}%", flush=True)

    logger.info("Running target: %s", target.name)
    logger.info("  Platform: %s", target.platform)
    logger.info("  Keywords: %s", target.filters.keywords)
    logger.info("  Countries: %s", target.filters.countries)
    logger.info("  Modalities: %s", target.filters.modalities)
    logger.info("  Date: %s", target.filters.date_range)

    if target.platform == "linkedin":
        async with LinkedInScraper(db=db, headless=True) as scraper:
            # Build LinkedIn search params from filters
            params = target.filters.to_linkedin_params()
            query = params.get("keywords", "")
            location = params.get("location", "")

            jobs = await scraper.scrape_search(
                query=query,
                location=location,
                max_results=target.max_results,
            )

            # Search phase done — 20% of target allocation
            emit_progress(20)

            # Apply global limit when set (debug mode: stop after 3 total)
            if max_jobs is not None:
                jobs = jobs[:max_jobs]

            # Enrich each job with detail page (80% of target allocation)
            enriched = []
            for i, job in enumerate(jobs):
                try:
                    detail = await scraper.scrape_detail(job.url)
                    if detail.description:
                        job.description = detail.description
                    job = scraper.auto_detect_tags(job)
                except Exception as e:
                    logger.warning("Failed to enrich '%s': %s", job.title, e)

                # Apply post-scrape modalidad filter
                if target.filters.matches_job(job):
                    scraper.save_job(job)
                    enriched.append(job)

                # Emit progress after each enrichment
                enrich_pct = 20 + ((i + 1) / len(jobs)) * 80 if jobs else 100
                emit_progress(enrich_pct)

                # Stop early when global limit is reached
                if max_jobs is not None and len(enriched) >= max_jobs:
                    break

            logger.info("Target '%s': %d/%d jobs passed filters", target.name, len(enriched), len(jobs))
            return enriched
    else:
        logger.error("Unsupported platform: %s", target.platform)
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
        enabled = [t for t in enabled if t.platform == scan_platform]

    logger.info("Loaded %d targets (%d enabled)", len(targets), len(enabled))

    db = JobDatabase(DB_PATH)
    all_jobs = []
    total = len(enabled)
    completed = 0

    # Debug mode: stop scan completely after N total results
    debug_mode = os.environ.get("DEBUG_MODE")
    debug_limit = int(debug_mode) if debug_mode else None

    for i, target in enumerate(enabled):
        remaining = None
        if debug_limit is not None:
            remaining = debug_limit - len(all_jobs)
            if remaining <= 0:
                logger.info("Debug mode: reached %d jobs, stopping scan", debug_limit)
                break

        jobs = await run_target(target, db, target_index=i, total_targets=total, max_jobs=remaining)
        all_jobs.extend(jobs)
        completed += 1

    # Post-scrape keyword filter (from SCAN_KEYWORD env var)
    scan_keyword = os.environ.get("SCAN_KEYWORD", "").strip()
    if scan_keyword:
        kw_lower = scan_keyword.lower()
        before = len(all_jobs)
        all_jobs = [
            job for job in all_jobs
            if kw_lower in job.title.lower() or kw_lower in (job.company or "").lower()
        ]
        after = len(all_jobs)
        logger.info("SCAN_KEYWORD filter '%s': %d → %d jobs", scan_keyword, before, after)

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

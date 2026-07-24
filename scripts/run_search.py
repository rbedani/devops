#!/usr/bin/env python3
"""Run job search using configured targets."""

import asyncio
import json
import logging
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


async def run_target(target: SearchTarget, db: JobDatabase) -> list:
    """Execute a single search target and return jobs found."""
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

            # Enrich each job with detail page
            enriched = []
            for job in jobs:
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
    logger.info("Loaded %d targets (%d enabled)", len(targets), len(enabled))

    db = JobDatabase(DB_PATH)
    all_jobs = []

    for target in enabled:
        jobs = await run_target(target, db)
        all_jobs.extend(jobs)

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

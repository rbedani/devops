#!/usr/bin/env python3
"""Enrich existing jobs by scraping their detail pages."""

import asyncio
import json
import logging
from datetime import datetime

from src.scrapers.linkedin import LinkedInScraper
from src.db.database import JobDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    db = JobDatabase("jobs.db")

    # Load all jobs from DB
    with db:
        jobs = db.get_all(limit=100)
        logger.info("Found %d jobs in DB to enrich", len(jobs))

    if not jobs:
        logger.warning("No jobs in DB. Run test_scrape.py first.")
        return

    async with LinkedInScraper(db=db, headless=True) as scraper:
        enriched = 0
        for i, job in enumerate(jobs, 1):
            logger.info("[%d/%d] Enriching: %s", i, len(jobs), job.title)
            try:
                detail = await scraper.scrape_detail(job.url)

                # Merge description (detail has the full text)
                if detail.description:
                    job.description = detail.description

                # Re-run tag detection with enriched data
                job = scraper.auto_detect_tags(job)

                # Re-save to DB
                db.upsert_job(job)
                enriched += 1

                # Print what we found
                desc_preview = job.description[:150].replace("\n", " ") if job.description else "(no desc)"
                print(f"\n--- [{i}/{len(jobs)}] {job.title} ---")
                print(f"  Company:  {job.company}")
                print(f"  Location: {job.location}")
                print(f"  Desc:     {desc_preview}...")
                print(f"  Tags:")
                for tag in job.tags:
                    print(f"    {tag.key}: {tag.value} (conf={tag.confidence})")

            except Exception as e:
                logger.error("Failed to enrich '%s': %s", job.title, e)

        print(f"\n{'=' * 70}")
        print(f"  Enriched {enriched}/{len(jobs)} jobs")
        print(f"  DB total: {db.count()} jobs")
        print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())

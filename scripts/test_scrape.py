#!/usr/bin/env python3
"""Quick test: scrape LinkedIn jobs and save to SQLite."""

import asyncio
import json
import logging

from src.scrapers.linkedin import LinkedInScraper
from src.db.database import JobDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

QUERY = "DevOps engineer"
LOCATION = "Argentina"
MAX_RESULTS = 10


async def main():
    db = JobDatabase("jobs.db")

    async with LinkedInScraper(db=db, headless=True) as scraper:
        logger.info("Scraping LinkedIn for '%s' in '%s'...", QUERY, LOCATION)
        jobs = await scraper.scrape_search(QUERY, LOCATION, max_results=MAX_RESULTS)

        if not jobs:
            logger.warning("No jobs found. LinkedIn might require login or cookies.")
            return

        # Save to DB (auto-detects tags)
        ids = scraper.save_many(jobs)
        logger.info("Saved %d jobs to DB (ids: %s)", len(ids), ids)

        # Print results
        print("\n" + "=" * 70)
        print(f"  RESULTS: {len(jobs)} jobs scraped from LinkedIn")
        print("=" * 70)

        for i, job in enumerate(jobs, 1):
            print(f"\n--- Job {i} ---")
            print(f"  Title:    {job.title}")
            print(f"  Company:  {job.company or 'N/A'}")
            print(f"  Location: {job.location or 'N/A'}")
            print(f"  URL:      {job.url}")
            print(f"  Tags:")
            for tag in job.tags:
                print(f"    {tag.key}: {tag.value} (conf={tag.confidence})")
            if not job.tags:
                print("    (no tags detected yet)")

        # DB stats
        print(f"\n{'=' * 70}")
        print(f"  DB total: {db.count()} jobs")
        print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())

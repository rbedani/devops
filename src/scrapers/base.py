"""Base scraper abstraction.

Every site-specific scraper inherits from BaseScraper and implements:
  - login()            → authenticate if needed
  - scrape_search()    → scrape search results for a query
  - scrape_detail()    → scrape a single job detail page

The base class handles tag auto-detection and DB persistence automatically.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.core.db.database import JobDatabase
from src.core.models.job import Job
from src.tags.detector import TagRegistry, build_default_registry

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base for all job site scrapers."""

    SOURCE: str = "unknown"

    def __init__(
        self,
        db: JobDatabase | None = None,
        tag_registry: TagRegistry | None = None,
        headless: bool = True,
    ) -> None:
        self.db = db or JobDatabase()
        self.registry = tag_registry or build_default_registry()
        self.headless = headless
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # -- Lifecycle --------------------------------------------------------------

    async def __aenter__(self) -> BaseScraper:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()

    async def start(self) -> None:
        """Launch browser and create a page."""
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        self._page = await self._context.new_page()
        logger.info("Browser launched for %s scraper", self.SOURCE)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self.db.close()
        logger.info("Browser closed for %s scraper", self.SOURCE)

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Scraper not started. Use 'async with scraper' or call start().")
        return self._page

    # -- Tag detection ----------------------------------------------------------

    def auto_detect_tags(self, job: Job) -> Job:
        """Run all registered tag detectors on a job and attach results."""
        metadata = {}
        applicants = job.get_tag("postulados")
        if applicants is not None:
            metadata["applicants"] = applicants
        published_date = job.get_tag("fecha_publicacion")
        if published_date is not None:
            metadata["published_date"] = published_date
        detected = self.registry.detect_all(
            title=job.title,
            description=job.description,
            metadata=metadata,
        )
        for tag in detected:
            existing = job.get_tag(tag.key)
            if existing is None:
                job.set_tag(tag.key, tag.value, tag.confidence)
        return job

    # -- Persistence ------------------------------------------------------------

    def save_job(self, job: Job) -> int:
        """Auto-detect tags and upsert to database. Returns row id."""
        job = self.auto_detect_tags(job)
        row_id = self.db.upsert_job(job)
        logger.info("Saved job %r (id=%s)", job.title, row_id)
        return row_id

    def save_many(self, jobs: list[Job]) -> list[int]:
        """Auto-detect tags on all jobs and batch upsert."""
        return [self.save_job(j) for j in jobs]

    # -- Abstract methods (site-specific) ---------------------------------------

    @abstractmethod
    async def login(self, credentials: dict[str, str]) -> None:
        """Authenticate with the site if required."""
        ...

    @abstractmethod
    async def scrape_search(self, query: str, location: str = "", max_results: int = 25) -> list[Job]:  # noqa: E501
        """Search for jobs and return a list of Job objects."""
        ...

    @abstractmethod
    async def scrape_detail(self, url: str) -> Job:
        """Scrape the full detail of a single job listing."""
        ...

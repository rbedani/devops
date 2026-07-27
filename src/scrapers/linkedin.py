"""LinkedIn job scraper.

Uses Playwright to navigate LinkedIn's job search, extract listings,
and auto-detect metadata tags.  No API key required — works via browser.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlencode

from playwright.async_api import TimeoutError as PwTimeout

from src.core.models.job import Job
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search/"


class LinkedInScraper(BaseScraper):
    """Scrape job listings from LinkedIn Jobs."""

    SOURCE = "linkedin"

    async def login(self, credentials: dict[str, str]) -> None:
        """Login to LinkedIn with email/password."""
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        if not email or not password:
            logger.warning("No LinkedIn credentials provided — proceeding without login")
            return

        await self.page.goto("https://www.linkedin.com/login")
        await self.page.fill('input[name="session_key"]', email)
        await self.page.fill('input[name="session_password"]', password)
        await self.page.click('button[type="submit"]')
        await self.page.wait_for_load_state("networkidle", timeout=15000)
        logger.info("LinkedIn login completed")

    async def scrape_search(
        self,
        query: str,
        location: str = "",
        max_results: int = 25,
        extra_params: dict[str, str] | None = None,
    ) -> list[Job]:
        """Search LinkedIn Jobs and extract listings.

        extra_params: Additional LinkedIn search URL parameters
        (e.g. f_TPR=r604800 for last week, f_WT=2 for remote).
        These are merged into the search URL query string.
        """
        params = {"keywords": query}
        if location:
            params["location"] = location
        if extra_params:
            params.update(extra_params)

        url = f"{LINKEDIN_JOBS_URL}?{urlencode(params)}"
        logger.info("Navigating to: %s", url)

        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except PwTimeout:
            logger.warning("Timeout loading search page: %s", url)
            return []

        await self.page.wait_for_timeout(3000)  # let JS render

        jobs: list[Job] = []

        # LinkedIn renders job cards in a list container
        cards = await self.page.query_selector_all(".base-card, .job-search-card")
        logger.info("Found %d job cards", len(cards))

        for card in cards[:max_results]:
            try:
                job = await self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.warning("Failed to parse card: %s", e)

        logger.info("Scraped %d jobs from LinkedIn", len(jobs))
        return jobs

    async def _parse_card(self, card: any) -> Job | None:
        """Extract job data from a single LinkedIn job card element."""
        # Title + URL
        title_el = await card.query_selector("a.base-card__full-link, a.job-search-card__title-link")
        if not title_el:
            return None

        title = (await title_el.inner_text()).strip()
        href = await title_el.get_attribute("href")
        url = href.split("?")[0] if href else ""

        if not title or not url:
            return None

        # Company
        company_el = await card.query_selector("h4.base-search-card__subtitle, a.hidden-nested-link")
        company = (await company_el.inner_text()).strip() if company_el else ""

        # Location
        loc_el = await card.query_selector(".job-search-card__location")
        location = (await loc_el.inner_text()).strip() if loc_el else ""

        # Date
        date_el = await card.query_selector("time")
        date_str = ""
        if date_el:
            date_str = await date_el.get_attribute("datetime") or (await date_el.inner_text()).strip()

        # Applicants count
        applicants_el = await card.query_selector(".num-applicants__caption, .results-context-header__job-count")
        applicants = (await applicants_el.inner_text()).strip() if applicants_el else ""

        job = Job(
            source=self.SOURCE,
            title=title,
            url=url,
            company=company,
            location=location,
        )

        if date_str:
            job.set_tag("fecha_publicacion", date_str, 1.0)
        if applicants:
            job.set_tag("postulados", applicants, 0.9)

        return job

    async def scrape_detail(self, url: str) -> Job:
        """Scrape the full detail page of a LinkedIn job."""
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except PwTimeout:
            logger.warning("Timeout loading detail page: %s", url)
            return Job(source=self.SOURCE, title="", url=url)

        await self.page.wait_for_timeout(3000)

        title = await self._safe_text(".top-card-layout__title, h1")
        company = await self._safe_text(".topcard__org-name-link, .top-card-layout__second-subtitle")
        location = await self._safe_text(".topcard__flavor--bullet, .top-card-layout__first-subtitle")
        description_el = await self.page.query_selector(".description__text, .show-more-less-html__markup")
        description = (await description_el.inner_text()).strip() if description_el else ""

        job = Job(
            source=self.SOURCE,
            title=title,
            url=url.split("?")[0],
            company=company,
            location=location,
            description=description,
        )

        return job

    async def _safe_text(self, selector: str) -> str:
        el = await self.page.query_selector(selector)
        return (await el.inner_text()).strip() if el else ""

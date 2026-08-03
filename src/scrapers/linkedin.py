"""LinkedIn job scraper.

Uses Playwright to navigate LinkedIn's job search, extract listings,
and auto-detect metadata tags.  No API key required — works via browser.
"""

from __future__ import annotations

import asyncio
import logging
import random
from urllib.parse import urlencode

from playwright.async_api import TimeoutError as PwTimeout

from src.core.models.job import Job
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search/"

# D5 — LinkedIn paginates with a start offset in steps of 25 (page 1 = start 0).
LINKEDIN_PAGE_SIZE = 25


def _build_search_url(
    query: str = "",
    location: str = "",
    extra_params: dict[str, str] | None = None,
    start: int = 0,
) -> str:
    """Build a LinkedIn Jobs search URL with query-string parameters.

    Pagination uses the start offset: page N → start=25*(N-1); start=0 adds
    no parameter (page 1). extra_params (native filters like f_TPR/f_WT) are
    merged into EVERY page URL unchanged (spec: native filter application).
    """
    params: dict[str, str] = {}
    if query:
        params["keywords"] = query
    if location:
        params["location"] = location
    if extra_params:
        params.update(extra_params)
    if start > 0:
        params["start"] = str(start)
    return f"{LINKEDIN_JOBS_URL}?{urlencode(params)}"


class LinkedInScraper(BaseScraper):
    """Scrape job listings from LinkedIn Jobs."""

    SOURCE = "linkedin"

    # Static URL builder exposed for unit testing
    build_search_url = staticmethod(_build_search_url)

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
        max_results: int | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> list[Job]:
        """Search LinkedIn Jobs and extract listings with pagination (D5/D6).

        Walks result pages in steps of 25 (start=25*(page-1)) until
        max_results is reached or a page yields zero new cards (last-page
        detection). extra_params (f_TPR, f_WT, ...) are merged into every
        page URL. A mid-walk timeout/block stops the walk, keeps the cards
        already collected, logs a warning, and returns them. max_results=None
        means no cap (production walk to the last page).
        """
        jobs: list[Job] = []
        seen_urls: set[str] = set()
        page = 1

        while max_results is None or len(jobs) < max_results:
            url = _build_search_url(
                query=query,
                location=location,
                extra_params=extra_params,
                start=(page - 1) * LINKEDIN_PAGE_SIZE,
            )
            logger.info("LinkedIn search page %d: %s", page, url)

            # Navigate with timeout protection — mid-walk failure keeps cards
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except PwTimeout:
                logger.warning("Timeout loading LinkedIn search: %s", url)
                break
            except Exception as e:
                logger.warning("Navigation error on LinkedIn: %s", e)
                break

            # Anti-bot delay: 1–3s random (serial cadence, same as Indeed)
            delay = random.uniform(1.0, 3.0)
            logger.debug("LinkedIn anti-bot delay: %.1fs", delay)
            await asyncio.sleep(delay)

            # LinkedIn renders job cards in a list container
            cards = await self.page.query_selector_all(".base-card, .job-search-card")
            logger.info("LinkedIn page %d: found %d cards", page, len(cards))

            if not cards:
                break

            page_jobs = 0
            for card in cards:
                try:
                    job = await self._parse_card(card)
                except Exception as e:
                    logger.warning("Failed to parse LinkedIn card: %s", e)
                    continue
                if not job or not job.url:
                    continue

                # Deduplicate by URL within the walk
                if job.url in seen_urls:
                    continue
                seen_urls.add(job.url)

                jobs.append(job)
                page_jobs += 1

                # Early exit on max_results
                if max_results is not None and len(jobs) >= max_results:
                    break

            logger.info("LinkedIn page %d: %d new jobs (total %d)",
                        page, page_jobs, len(jobs))

            # Last-page detection: a page with zero NEW cards ends the walk
            if page_jobs == 0:
                break

            page += 1

        logger.info("LinkedIn scrape_search complete: %d jobs from %d pages",
                    len(jobs), page)
        return jobs if max_results is None else jobs[:max_results]

    async def _parse_card(self, card: any) -> Job | None:
        """Extract job data from a single LinkedIn job card element."""
        # Title + URL
        title_el = await card.query_selector("a.base-card__full-link, a.job-search-card__title-link")  # noqa: E501
        if not title_el:
            return None

        title = (await title_el.inner_text()).strip()
        href = await title_el.get_attribute("href")
        url = href.split("?")[0] if href else ""

        if not title or not url:
            return None

        # Company
        company_el = await card.query_selector("h4.base-search-card__subtitle, a.hidden-nested-link")  # noqa: E501
        company = (await company_el.inner_text()).strip() if company_el else ""

        # Location
        loc_el = await card.query_selector(".job-search-card__location")
        location = (await loc_el.inner_text()).strip() if loc_el else ""

        # Date
        date_el = await card.query_selector("time")
        date_str = ""
        if date_el:
            date_str = await date_el.get_attribute("datetime") or (await date_el.inner_text()).strip()  # noqa: E501

        # Applicants count
        applicants_el = await card.query_selector(".num-applicants__caption, .results-context-header__job-count")  # noqa: E501
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
        company = await self._safe_text(".topcard__org-name-link, .top-card-layout__second-subtitle")  # noqa: E501
        location = await self._safe_text(".topcard__flavor--bullet, .top-card-layout__first-subtitle")  # noqa: E501
        description_el = await self.page.query_selector(".description__text, .show-more-less-html__markup")  # noqa: E501
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

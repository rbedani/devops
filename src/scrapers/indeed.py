"""Indeed job scraper (es.indeed.com).

Uses Playwright to navigate Indeed's public job search, extract listings
from cards with multiple fallback CSS selectors, and enrich from detail pages.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any
from urllib.parse import urlencode

from playwright.async_api import TimeoutError as PwTimeout

from src.core.models.job import Job
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

INDEED_SEARCH_URL = "https://es.indeed.com/jobs"
INDEED_VIEWJOB_URL = "https://es.indeed.com/viewjob"

# ---------------------------------------------------------------------------
# URL builders (pure functions — trivially testable without Playwright)
# ---------------------------------------------------------------------------


def _build_search_url(
    query: str = "",
    location: str = "",
    fromage: int | None = None,
    jt: str | None = None,
    start: int = 0,
) -> str:
    """Build an Indeed search URL with query-string parameters."""
    params: dict[str, str] = {}
    if query:
        params["q"] = query
    if location:
        params["l"] = location
    if fromage is not None:
        params["fromage"] = str(fromage)
    if jt is not None:
        params["jt"] = jt
    if start > 0:
        params["start"] = str(start)

    qs = urlencode(params)
    return f"{INDEED_SEARCH_URL}?{qs}" if qs else INDEED_SEARCH_URL


def _build_detail_url(jk: str) -> str:
    """Build an Indeed viewjob URL from a data-jk value."""
    return f"{INDEED_VIEWJOB_URL}?jk={jk}"


# ---------------------------------------------------------------------------
# Card parser (pure function — testable without Playwright)
# ---------------------------------------------------------------------------


def _parse_card_from_data(card: dict[str, Any]) -> Job | None:
    """Parse a job card from pre-extracted data (unit-testable).

    Production code extracts the dict from Playwright card elements,
    then passes to this function for deterministic parsing.
    """
    title = (card.get("title") or "").strip()
    if not title:
        return None

    company = (card.get("company") or "").strip()
    location = (card.get("location") or "").strip()
    data_jk = (card.get("data_jk") or "").strip()

    url = _build_detail_url(data_jk) if data_jk else ""

    job = Job(
        source="indeed",
        title=title,
        url=url,
        company=company,
        location=location,
    )

    salary = (card.get("salary") or "").strip()
    if salary:
        job.set_tag("salario", salary, 0.9)

    date_str = (card.get("date") or "").strip()
    if date_str:
        job.set_tag("fecha_publicacion", date_str, 0.9)

    return job


# ---------------------------------------------------------------------------
# Scraper class
# ---------------------------------------------------------------------------


class IndeedScraper(BaseScraper):
    """Scrape job listings from Indeed (Spain)."""

    SOURCE = "indeed"

    # Static URL builders exposed for unit testing
    build_search_url = staticmethod(_build_search_url)
    build_detail_url = staticmethod(_build_detail_url)
    _parse_card_from_data = staticmethod(_parse_card_from_data)

    # -- Abstract method implementations --------------------------------------

    async def login(self, credentials: dict[str, str]) -> None:
        """Indeed public search requires no authentication — no-op."""
        logger.info("Indeed — no login required for public search")

    async def scrape_search(
        self,
        query: str,
        location: str = "",
        max_results: int = 25,
        extra_params: dict[str, str] | None = None,
    ) -> list[Job]:
        """Search Indeed and extract job listings with pagination.

        Paginates in steps of 10 (start=0,10,20...) until max_results
        is reached or a page returns zero cards.
        """
        # Resolve fromage from extra_params or default to None
        fromage_val: int | None = None
        if extra_params and "fromage" in extra_params:
            try:
                fromage_val = int(extra_params["fromage"])
            except (ValueError, TypeError):
                fromage_val = None

        # Resolve jt from extra_params or default to None
        jt_val: str | None = None
        if extra_params and "jt" in extra_params:
            jt_val = extra_params["jt"]

        jobs: list[Job] = []
        seen_jks: set[str] = set()
        start = 0

        while len(jobs) < max_results:
            url = _build_search_url(
                query=query,
                location=location,
                fromage=fromage_val,
                jt=jt_val,
                start=start,
            )
            logger.info("Indeed search page %d: %s", start // 10 + 1, url)

            # Navigate with timeout protection
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except PwTimeout:
                logger.warning("Timeout loading Indeed search: %s", url)
                break
            except Exception as e:
                logger.warning("Navigation error on Indeed: %s", e)
                break

            # Anti-bot delay: 1–3s random
            delay = random.uniform(1.0, 3.0)
            logger.debug("Indeed anti-bot delay: %.1fs", delay)
            await asyncio.sleep(delay)

            # Extract cards with fallback selectors
            cards = await self.page.query_selector_all(
                ".job_seen_beacon, "
                ".jobsearch-ResultsList > li, "
                "li[data-jk], "
                ".resultContent"
            )
            logger.info("Indeed page %d: found %d cards", start // 10 + 1, len(cards))

            if not cards:
                # Could be empty results page or anti-bot block
                body_text = await self.page.inner_text("body")
                if "no matching jobs" in body_text.lower() or "no results" in body_text.lower():
                    logger.info("Indeed: no matching jobs found")
                break

            page_jobs = 0
            for card in cards:
                try:
                    card_data = await self._extract_card_data(card)
                except Exception as e:
                    logger.warning("Failed to extract Indeed card data: %s", e)
                    continue

                data_jk = card_data.get("data_jk", "")
                if not data_jk:
                    continue

                # Deduplicate by data-jk
                if data_jk in seen_jks:
                    continue
                seen_jks.add(data_jk)

                job = _parse_card_from_data(card_data)
                if job:
                    jobs.append(job)
                    page_jobs += 1

                # Early exit on max_results
                if len(jobs) >= max_results:
                    break

            logger.info("Indeed page %d: %d new jobs (total %d)",
                        start // 10 + 1, page_jobs, len(jobs))

            if page_jobs == 0:
                break

            start += 10

        logger.info("Indeed scrape_search complete: %d jobs from %d pages",
                    len(jobs), start // 10 + 1)
        return jobs[:max_results]

    async def scrape_detail(self, url: str) -> Job:
        """Scrape the full detail page of an Indeed job listing.

        Extracts the description from div#jobDescriptionText.
        On failure, returns a Job with empty description — never crashes.
        """
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except (PwTimeout, Exception) as e:
            logger.warning("Indeed detail page timeout/error for %s: %s", url, e)
            return Job(source=self.SOURCE, title="", url=url)

        await asyncio.sleep(random.uniform(1.0, 3.0))

        description = ""
        try:
            desc_el = await self.page.query_selector(
                "div#jobDescriptionText, "
                "#jobDescriptionText, "
                "[data-testid=\"jobDescriptionText\"]"
            )
            if desc_el:
                description = (await desc_el.inner_text()).strip()
        except Exception as e:
            logger.warning("Indeed detail extraction error for %s: %s", url, e)

        return Job(
            source=self.SOURCE,
            title="",
            url=url,
            description=description,
        )

    # -- Internal helpers ----------------------------------------------------

    async def _extract_card_data(self, card: Any) -> dict[str, Any]:
        """Extract raw data from a Playwright card element.

        Uses multiple fallback selectors per field for resilience against
        Indeed's frequently-changing class names.
        """
        data: dict[str, Any] = {}

        # data-jk (job key)
        data_jk = await card.get_attribute("data-jk")
        if not data_jk:
            jk_el = await card.query_selector("[data-jk]")
            if jk_el:
                data_jk = await jk_el.get_attribute("data-jk")
        data["data_jk"] = data_jk or ""

        # Title — fallback selectors
        title = ""
        for sel in (
            "h2.jobTitle a",
            ".jobTitle > a",
            "a[id^=\"job_\"]",
            "[data-testid=\"jobTitle\"] a",
        ):
            el = await card.query_selector(sel)
            if el:
                title = (await el.inner_text()).strip()
                if title:
                    break
        data["title"] = title

        # Company — fallback selectors
        company = ""
        for sel in (
            "[data-testid=\"company-name\"]",
            ".companyName",
            ".company_location span[data-testid]",
            "span[data-testid=\"company-name\"]",
        ):
            el = await card.query_selector(sel)
            if el:
                company = (await el.inner_text()).strip()
                if company:
                    break
        data["company"] = company

        # Location — fallback selectors
        location = ""
        for sel in (
            "[data-testid=\"text-location\"]",
            ".companyLocation",
            "div[data-testid=\"text-location\"]",
        ):
            el = await card.query_selector(sel)
            if el:
                location = (await el.inner_text()).strip()
                if location:
                    break
        data["location"] = location

        # Salary — fallback selectors
        salary = ""
        for sel in (
            "[data-testid=\"estimated-salary\"]",
            ".salary-snippet-container",
            ".salaryList",
        ):
            el = await card.query_selector(sel)
            if el:
                salary = (await el.inner_text()).strip()
                if salary:
                    break
        data["salary"] = salary

        # Date — fallback selectors (Indeed shows relative text like "Hace 3 días")
        date_str = ""
        for sel in (
            "[data-testid=\"myJobsStateDate\"]",
            "span[data-testid=\"myJobsStateDate\"]",
            ".jobsearch-JobMetadataFooter-item:last-child",
            "time",
            "[class*=\"date\"]",
        ):
            el = await card.query_selector(sel)
            if el:
                date_str = (await el.get_attribute("datetime")) or (await el.inner_text()).strip()
                if date_str:
                    break
        data["date"] = date_str

        return data
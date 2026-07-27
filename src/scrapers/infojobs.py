"""InfoJobs job scraper (infojobs.net).

Uses Playwright to navigate InfoJobs' job search, extract listings,
and auto-detect metadata tags.  No API key required — works via browser.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from playwright.async_api import TimeoutError as PwTimeout

from src.core.models.job import Job
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

INFOJOBS_SEARCH_URL = "https://www.infojobs.net/jobsearch/search-results/list.xhtml"


class InfoJobsScraper(BaseScraper):
    """Scrape job listings from InfoJobs (Spain)."""

    SOURCE = "infojobs"

    async def login(self, credentials: dict[str, str]) -> None:
        """InfoJobs doesn't require login to search — no-op."""
        logger.info("InfoJobs — no login required for search")

    async def scrape_search(
        self,
        query: str,
        location: str = "",
        max_results: int = 25,
        extra_params: dict[str, str] | None = None,
    ) -> list[Job]:
        """Search InfoJobs and extract listings.

        extra_params: Additional search URL parameters (e.g. date range).
        These are merged into the search URL query string.
        """
        params: dict[str, str] = {}
        if query:
            params["keyword"] = query
        if location:
            params["city"] = location
        if extra_params:
            params.update(extra_params)

        url = f"{INFOJOBS_SEARCH_URL}?{urlencode(params)}" if params else INFOJOBS_SEARCH_URL
        logger.info("Navigating to: %s", url)

        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except PwTimeout:
            logger.warning("Timeout loading search page: %s", url)
            return []

        await self.page.wait_for_timeout(3000)  # let JS render

        jobs: list[Job] = []

        # InfoJobs renders job cards — try common selector patterns
        cards = await self.page.query_selector_all(
            ".ij-OfferCardContent, "
            ".ij-OfferCard, "
            "article[class*='offer'], "
            ".card-offer, "
            "[id*='offer-result-']"
        )
        logger.info("Found %d job cards on InfoJobs", len(cards))

        for card in cards[:max_results]:
            try:
                job = await self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.warning("Failed to parse InfoJobs card: %s", e)

        logger.info("Scraped %d jobs from InfoJobs", len(jobs))
        return jobs

    async def _parse_card(self, card: any) -> Job | None:
        """Extract job data from a single InfoJobs job card element."""
        # Title — use the job title link (not the company subtitle link)
        title_el = await card.query_selector(
            ".ij-OfferCardContent-description-title a"
        )
        if not title_el:
            return None

        title = (await title_el.inner_text()).strip()
        href = await title_el.get_attribute("href")
        if not href or not title:
            return None

        # Make URL absolute
        if href.startswith("//"):
            url = f"https:{href}"
        elif href.startswith("/"):
            url = f"https://www.infojobs.net{href}"
        else:
            url = href

        # Company — subtitle element
        company_el = await card.query_selector(".ij-OfferCardContent-description-subtitle")
        company = (await company_el.inner_text()).strip() if company_el else ""

        # Location — InfoJobs cards embed location in a city/country element
        loc_el = await card.query_selector(
            ".ij-OfferCardContent-description-location, "
            "[class*='city'], "
            "[class*='City']"
        )
        location = (await loc_el.inner_text()).strip() if loc_el else ""

        # Date — InfoJobs uses .ij-FormatterSincedate
        date_el = await card.query_selector(".ij-FormatterSincedate, time, [class*='date']")
        date_str = ""
        if date_el:
            date_str = (
                await date_el.get_attribute("datetime")
                or (await date_el.inner_text()).strip()
            )

        # Salary — if present on the card
        salary_el = await card.query_selector(
            ".ij-OfferCardContent-description-salary-info, [class*='salary']"
        )
        salary_str = (await salary_el.inner_text()).strip() if salary_el else ""

        job = Job(
            source=self.SOURCE,
            title=title,
            url=url.split("?")[0],
            company=company,
            location=location,
        )

        if date_str:
            job.set_tag("fecha_publicacion", date_str, 1.0)
        if salary_str:
            job.set_tag("salario", salary_str, 0.9)

        return job

    async def scrape_detail(self, url: str) -> Job:
        """Scrape the full detail page of an InfoJobs job.

        Extracts structured header data (location, modality, salary)
        and the full job description from the body text.
        """
        try:
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
        except PwTimeout:
            logger.warning("Timeout loading detail page: %s", url)
            return Job(source=self.SOURCE, title="", url=url)

        await self.page.wait_for_timeout(3000)

        # --- Header: structured data ---
        header_el = await self.page.query_selector(
            ".ij-OfferDetailHeader-content, article, .ij-OfferDetail"
        )
        header_text = (await header_el.inner_text()).strip() if header_el else ""

        # Parse header lines for structured fields
        title = ""
        company = ""
        location = ""
        modality = ""
        salary = ""

        lines = header_text.split("\n")
        title = lines[0] if lines else ""

        for line in lines:
            ls = line.strip()
            if not ls:
                continue
            # Salary: "20.000€ - 20.000€ Bruto/año" (skip "Salario no disponible")
            if "€" in ls and ("bruto" in ls.lower() or "año" in ls.lower()):
                if "no disponible" not in ls.lower():
                    salary = ls
            # Modality: "Presencial", "Remoto", "Híbrido", "Teletrabajo", "Solo teletrabajo"
            elif ls.lower().replace("solo ", "") in (
                "presencial", "remoto", "híbrido", "hibrido", "teletrabajo",
            ):
                modality = ls
            # Location: "Madrid (Madrid)" — must have alpha chars, not just numbers
            elif (
                "(" in ls
                and "guardar" not in ls.lower()
                and ls != title
                and any(c.isalpha() for c in ls.split("(")[0])
                and len(ls) < 100
            ):
                location = ls

        # If no location from header, try company (line after Guardar)
        if not company:
            for i, line in enumerate(lines):
                if line.strip() == "Guardar" and i + 1 < len(lines):
                    company = lines[i + 1].strip()
                    break

        # --- Full description ---
        body_text = await self.page.inner_text("body")
        description = ""

        # Find the "Descripción" section
        for marker in ("Descripción", "Descripcion", "Funciones", "Requisitos"):
            idx = body_text.find(marker)
            if idx >= 0:
                # Grab from marker to end (or reasonable limit)
                description = body_text[idx:idx + 5000]
                break

        if not description:
            # Fallback: use body text without header
            description = body_text

        job = Job(
            source=self.SOURCE,
            title=title,
            url=url.split("?")[0],
            company=company,
            location=location,
            description=description,
        )

        if modality:
            job.set_tag("modalidad", modality, 0.9)
        if salary:
            job.set_tag("salario", salary, 0.9)

        return job

    async def _safe_text(self, selector: str) -> str:
        el = await self.page.query_selector(selector)
        return (await el.inner_text()).strip() if el else ""
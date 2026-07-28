"""Tecnoempleo job scraper (tecnoempleo.com).

Spain-focused job board. Uses Playwright to navigate server-rendered search
results, extract listings from card containers, and enrich from detail pages.
Follows the InfoJobs/Indeed patterns.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any
from urllib.parse import urlencode, quote

from playwright.async_api import TimeoutError as PwTimeout

from src.core.models.job import Job
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

TECNOEMPLEO_SEARCH_URL = "https://www.tecnoempleo.com/ofertas-trabajo"


# ---------------------------------------------------------------------------
# URL builders (pure functions — trivially testable without Playwright)
# ---------------------------------------------------------------------------


def _build_search_url(
    query: str = "",
    location: str = "",
    page: int = 1,
    en_remoto: bool = False,
) -> str:
    """Build a Tecnoempleo search URL with path segments and query params.

    Path: /ofertas-trabajo[/{location}]/{keyword-slug}
    Query: ?pagina={N}&en_remoto=%2C1%2C
    """
    # Build path segments
    segments: list[str] = [TECNOEMPLEO_SEARCH_URL]

    if location:
        segments.append(location.lower().strip())

    if query:
        slug = query.lower().strip().replace(" ", "-")
        segments.append(slug)

    url = "/".join(segments)

    # Query params
    params: dict[str, str] = {}
    if page > 1:
        params["pagina"] = str(page)
    if en_remoto:
        params["en_remoto"] = ",1,"

    if params:
        # Build query string manually to keep en_remoto=,1, unencoded
        parts: list[str] = []
        for k, v in params.items():
            if k == "en_remoto":
                parts.append(f"en_remoto={v}")  # keep commas unencoded
            else:
                parts.append(f"{quote(k)}={quote(v)}")
        return f"{url}?{'&'.join(parts)}"

    return url


# ---------------------------------------------------------------------------
# Card parser (pure function — unit-testable without Playwright)
# ---------------------------------------------------------------------------


def _parse_card_from_data(card: dict[str, Any]) -> Job | None:
    """Parse a job card from pre-extracted data (unit-testable).

    Production code extracts the dict from Playwright card elements,
    then passes to this function for deterministic parsing.

    Tag keys use Spanish: salario, fecha_publicacion, modalidad, tecnologias.
    """
    title = (card.get("title") or "").strip()
    if not title:
        return None

    company = (card.get("company") or "").strip()
    location = (card.get("location") or "").strip()
    url = (card.get("url") or "").strip()

    job = Job(
        source="tecnoempleo",
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

    # Modality from location (e.g. "Madrid (Hibrido)" -> "Hibrido")
    if location:
        match = re.search(r"\(([^)]+)\)", location)
        if match:
            modality = match.group(1).strip()
            if modality:
                job.set_tag("modalidad", modality, 0.9)
        elif "remoto" in location.lower():
            # "100% remoto", "En remoto", etc.
            job.set_tag("modalidad", location, 0.9)

    # Tech tags (space-separated on the page, pre-joined by extractor)
    tech_tags = card.get("tech_tags") or []
    if isinstance(tech_tags, list) and tech_tags:
        job.set_tag("tecnologias", ", ".join(tech_tags), 0.8)

    return job


# ---------------------------------------------------------------------------
# Scraper class
# ---------------------------------------------------------------------------


class TecnoempleoScraper(BaseScraper):
    """Scrape job listings from Tecnoempleo (Spain)."""

    SOURCE = "tecnoempleo"

    # Static methods exposed for unit testing
    build_search_url = staticmethod(_build_search_url)
    _parse_card_from_data = staticmethod(_parse_card_from_data)

    # -- Abstract method implementations --------------------------------------

    async def login(self, credentials: dict[str, str]) -> None:
        """Tecnoempleo public search requires no authentication — no-op."""
        logger.info("Tecnoempleo — no login required for public search")

    async def scrape_search(
        self,
        query: str,
        location: str = "",
        max_results: int = 25,
        extra_params: dict[str, str] | None = None,
    ) -> list[Job]:
        """Search Tecnoempleo and extract job listings with pagination.

        Paginates in steps of 30 (site default) until max_results is reached
        or a page returns zero cards.
        """
        # Resolve en_remoto from extra_params
        en_remoto: bool = False
        if extra_params and "en_remoto" in extra_params:
            en_remoto = extra_params["en_remoto"] == ",1,"

        jobs: list[Job] = []
        seen_urls: set[str] = set()
        page = 1

        while len(jobs) < max_results:
            url = _build_search_url(
                query=query,
                location=location,
                page=page,
                en_remoto=en_remoto,
            )
            logger.info("Tecnoempleo search page %d: %s", page, url)

            # Navigate with timeout protection
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except PwTimeout:
                logger.warning("Timeout loading Tecnoempleo search: %s", url)
                break
            except Exception as e:
                logger.warning("Navigation error on Tecnoempleo: %s", e)
                break

            # Anti-bot delay: 1–3s random
            delay = random.uniform(1.0, 3.0)
            logger.debug("Tecnoempleo anti-bot delay: %.1fs", delay)
            await asyncio.sleep(delay)

            # Check for 429/503 — exponential backoff
            status = await self.page.evaluate("() => document.title")
            if any(kw in status.lower() for kw in ("demasiadas", "bloqueado", "error")):
                logger.warning("Tecnoempleo anti-bot response: '%s'", status)
                break

            # Extract cards with fallback selectors
            cards = await self.page.query_selector_all(
                "div.p-3.border.rounded.mb-3.bg-white, "
                "div[id^='rf-'] + div.p-3.border, "
                "div.border.rounded.mb-3, "
                "div.p-3.border.mb-3"
            )
            logger.info("Tecnoempleo page %d: found %d cards", page, len(cards))

            if not cards:
                # Empty page — check if we hit the end
                body_text = await self.page.inner_text("body")
                if "sin resultados" in body_text.lower() or "no se han encontrado" in body_text.lower():
                    logger.info("Tecnoempleo: no matching jobs found")
                break

            page_jobs = 0
            for card in cards:
                try:
                    card_data = await self._extract_card_data(card)
                except Exception as e:
                    logger.warning("Failed to extract Tecnoempleo card data: %s", e)
                    continue

                url = card_data.get("url", "")
                if not url:
                    continue

                # Deduplicate by URL
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                job = _parse_card_from_data(card_data)
                if job:
                    jobs.append(job)
                    page_jobs += 1

                # Early exit on max_results
                if len(jobs) >= max_results:
                    break

            logger.info("Tecnoempleo page %d: %d new jobs (total %d)",
                        page, page_jobs, len(jobs))

            if page_jobs == 0:
                break

            page += 1

        logger.info("Tecnoempleo scrape_search complete: %d jobs from %d pages",
                    len(jobs), page)
        return jobs[:max_results]

    async def scrape_detail(self, url: str) -> Job:
        """Scrape the full detail page of a Tecnoempleo job listing.

        Extracts description, tech tags, and metadata from the detail page.
        On failure, returns a Job with empty description — never crashes.
        """
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except (PwTimeout, Exception) as e:
            logger.warning("Tecnoempleo detail page timeout/error for %s: %s", url, e)
            return Job(source=self.SOURCE, title="", url=url)

        await asyncio.sleep(random.uniform(1.0, 3.0))

        description = ""
        try:
            # Primary: the job description body
            for sel in (
                "section[class*='description']",
                "div[class*='description']",
                "div[class*='descripcion']",
                "article",
                "div[class*='content']",
                "div[class*='body']",
            ):
                desc_el = await self.page.query_selector(sel)
                if desc_el:
                    description = (await desc_el.inner_text()).strip()
                    if len(description) > 100:
                        break
        except Exception as e:
            logger.warning("Tecnoempleo detail extraction error for %s: %s", url, e)

        # Extract tech tags from detail page
        tech_tags: list[str] = []
        try:
            tag_els = await self.page.query_selector_all(
                "span.badge.bg-gray-500, "
                "span[class*='tag'], "
                "span[class*='badge'], "
                "span[class*='requirement']"
            )
            for tag_el in tag_els[:20]:
                t = (await tag_el.inner_text()).strip()
                if t and len(t) > 1 and len(t) < 50:
                    tech_tags.append(t)
        except Exception:
            pass

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
        Tecnoempleo's Bootstrap utility class structure.
        """
        data: dict[str, Any] = {}

        # URL — from onclick attribute on card div
        onclick = await card.get_attribute("onclick") or ""
        url = ""
        if onclick:
            match = re.search(r"location\.href='([^']+)'", onclick)
            if match:
                url = match.group(1)
        if not url:
            # Fallback: h3 > a link
            link_el = await card.query_selector("h3 a")
            if link_el:
                url = await link_el.get_attribute("href") or ""
        data["url"] = url

        # Title — h3 a
        title = ""
        for sel in (
            "h3 a.font-weight-bold",
            "h3 a",
            "a.font-weight-bold",
            "h3",
        ):
            el = await card.query_selector(sel)
            if el:
                title = (await el.inner_text()).strip()
                if title:
                    break
        data["title"] = title

        # Company — <a> with title containing "Ofertas de Empleo"
        company = ""
        for sel in (
            "a.text-primary.link-muted",
            "a.link-muted",
            "a[title*='Ofertas de Empleo']",
        ):
            el = await card.query_selector(sel)
            if el:
                company = (await el.inner_text()).strip()
                if company:
                    break
        data["company"] = company

        # Location — <b> inside the right column (col-lg-3)
        location = ""
        for sel in (
            "div.col-lg-3 b",
            "div.text-gray-700 b",
            "div.col-lg-3",
        ):
            el = await card.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                # Extract bold location from the text
                if sel.endswith("b"):
                    location = text
                else:
                    # Parse location from text block: "28/07/2026 Nueva\n\nMadrid (Presencial)\n..."
                    lines = text.split("\n")
                    for line in lines:
                        line = line.strip()
                        if line and not re.match(r"\d{2}/\d{2}/\d{4}", line):
                            if not line.startswith("Nueva") and not line.startswith("Actualizada"):
                                # Skip category lines that are short single words
                                if len(line) > 2 and not line.isupper():
                                    location = line
                                    break
                if location:
                    break
        data["location"] = location

        # Date — "DD/MM/YYYY" pattern in the right column
        date_str = ""
        for sel in (
            "div.col-lg-3",
            "div.text-gray-700",
        ):
            el = await card.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
                if match:
                    date_str = match.group(1)
                    break
        data["date"] = date_str

        # Salary — "XX.XXX€" pattern, appears after location in the card text
        salary = ""
        for sel in (
            "div.col-lg-3",
            "span.text-gray-800",
        ):
            el = await card.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                match = re.search(r"([\d.,]+€\s*[-–]\s*[\d.,]+€\s*(?:b/a)?)", text)
                if match:
                    salary = match.group(1).strip()
                    break
        data["salary"] = salary

        # Tech tags — .badge.bg-gray-500 spans
        tech_tags: list[str] = []
        tag_els = await card.query_selector_all(
            "span.badge.bg-gray-500, "
            "span.badge, "
            "span[class*='badge']"
        )
        for tag_el in tag_els[:20]:
            t = (await tag_el.inner_text()).strip()
            if t and len(t) > 1 and len(t) < 50:
                tech_tags.append(t)
        data["tech_tags"] = tech_tags

        return data
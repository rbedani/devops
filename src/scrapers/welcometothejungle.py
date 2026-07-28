"""Welcome to the Jungle job scraper — Algolia API based.

WTTJ's public job board was redesigned in mid-2026. The site no longer
renders job listings on the search page — it is a marketing landing page
gated behind profile creation. However, the Algolia search API that powers
the site still exposes job listings through a publicly-embedded client key.

This scraper queries Algolia directly instead of using Playwright CSR scraping.

Architecture:
  - Inherits from BaseScraper for tag detection, persistence, pipeline compat
  - Overrides start/stop to use httpx.AsyncClient instead of Playwright browser
  - scrape_search() queries Algolia with facet filters for country & contract type
  - All job data (title, company, salary, description) comes from the API hit
  - scrape_detail() is a passthrough — no second request needed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from src.core.models.job import Job
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Algolia configuration
# ---------------------------------------------------------------------------
# The search-only API key is embedded in the site's JavaScript and sitemap.
# It is restricted by referer (welcometothejungle.com) and only allows
# search queries on specific indices — it cannot list, browse, or delete.

ALGOLIA_APP_ID = "CSEKHVMS53"
ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
ALGOLIA_INDEX = "wttj_jobs_production_en"
ALGOLIA_BASE = f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net"

ALGOLIA_HEADERS = {
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "Content-Type": "application/json",
    "Referer": "https://www.welcometothejungle.com/",
    "Origin": "https://www.welcometothejungle.com",
}

# ---------------------------------------------------------------------------
# Shared mapping constants (mirrored in search.py to_wttj_params)
# ---------------------------------------------------------------------------

_COUNTRY_ISO: dict[str, str] = {
    "españa": "ES",
    "spain": "ES",
    "france": "FR",
    "germany": "DE",
    "uk": "GB",
    "united kingdom": "GB",
    "italy": "IT",
    "netherlands": "NL",
    "ireland": "IE",
    "portugal": "PT",
    "usa": "US",
    "us": "US",
}

_REMOTE_MAP: dict[str, str] = {
    "remoto": "full_time",
    "remote": "full_time",
    "hibrido": "partial",
    "hybrid": "partial",
    "presencial": "full_time",
    "onsite": "full_time",
}

_REMOTE_LABEL: dict[str, str] = {
    "full_time": "Remoto",
    "fulltime": "Remoto",
    "partial": "Híbrido/Hybrid",
    "no": "Presencial",
}

_DATE_DAYS: dict[str, int] = {
    "last_24h": 1,
    "last_week": 7,
    "last_month": 30,
}


# ---------------------------------------------------------------------------
# Scraper class
# ---------------------------------------------------------------------------


class WelcomeToTheJungleScraper(BaseScraper):
    """Scrape Welcome to the Jungle jobs via the public Algolia search API.

    Overrides BaseScraper lifecycle to use httpx instead of Playwright.
    The Algolia API key is embedded client-side and requires no auth.

    Usage:
        async with WelcomeToTheJungleScraper(db=db) as scraper:
            jobs = await scraper.scrape_search("devops", location="Spain")
    """

    SOURCE = "welcometothejungle"

    def __init__(self, **kwargs: Any) -> None:
        # Remove headless since we never launch a browser
        kwargs.pop("headless", None)
        super().__init__(**kwargs)
        self._client: httpx.AsyncClient | None = None

    # -- Lifecycle overrides (httpx, not Playwright) -------------------------

    async def start(self) -> None:
        self._client = httpx.AsyncClient(headers=ALGOLIA_HEADERS, timeout=15)

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self.db.close()

    @property
    def page(self) -> None:
        raise RuntimeError(
            "WelcomeToTheJungleScraper uses the Algolia API, not Playwright. "
            "No browser page is available."
        )

    # -- Abstract method implementations -------------------------------------

    async def login(self, credentials: dict[str, str]) -> None:
        """Algolia API is public — no authentication required."""
        logger.info("WelcomeToTheJungle — Algolia API requires no login")

    async def scrape_search(
        self,
        query: str = "",
        location: str = "",
        max_results: int = 25,
        extra_params: dict[str, str] | None = None,
    ) -> list[Job]:
        """Search WTTJ jobs via Algolia API.

        Args:
            query: Search keywords.
            location: Location name (e.g. "Spain", "France"). Maps to ISO code.
            max_results: Maximum number of jobs to return.
            extra_params: Optional dict with 'remote', 'days_ago' keys.

        Returns:
            List of Job objects with all available data from the API hit.
        """
        assert self._client is not None, "Scraper not started"

        # Resolve optional extra params
        remote_val: str = ""
        days_ago_val: int | None = None
        if extra_params:
            remote_val = extra_params.get("remote", "")
            days_ago_raw = extra_params.get("days_ago", "")
            if days_ago_raw:
                try:
                    days_ago_val = int(days_ago_raw)
                except (ValueError, TypeError):
                    days_ago_val = None

        # Build Algolia search params
        params_parts: list[str] = [f"hitsPerPage={max_results}"]

        if query:
            params_parts.insert(0, f"query={quote(query)}")

        # Build facet filters
        filters: list[str] = []

        # Country filter (ISO mapped from location name)
        if location:
            loc_lower = location.lower().strip()
            iso = _COUNTRY_ISO.get(loc_lower)
            if iso:
                filters.append(f'offices.country_code:"{iso}"')

        # Contract type filter (mapped from modality)
        if remote_val:
            filters.append(f'contract_type:"{remote_val}"')

        # Combine filters
        payload: dict[str, str] = {}
        if filters:
            payload["params"] = "&".join(
                params_parts + [f"filters={' AND '.join(filters)}"]
            )
        else:
            payload["params"] = "&".join(params_parts)

        logger.info(
            "WTTJ Algolia search: query=%r, location=%r, remote=%r",
            query, location, remote_val,
        )

        try:
            r = await self._client.post(
                f"{ALGOLIA_BASE}/1/indexes/{ALGOLIA_INDEX}/query",
                json=payload,
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning("WTTJ Algolia API error: %s", e)
            return []
        except httpx.RequestError as e:
            logger.warning("WTTJ Algolia request failed: %s", e)
            return []

        data = r.json()
        hits = data.get("hits", [])
        logger.info(
            "WTTJ Algolia: %d hits (total: %d) for query=%r",
            len(hits), data.get("nbHits", 0), query,
        )

        jobs: list[Job] = []
        current_date = datetime.now(timezone.utc)

        for hit in hits:
            try:
                job = self._hit_to_job(hit, current_date, days_ago_val)
                if job is not None:
                    jobs.append(job)
            except Exception as e:
                logger.warning("WTTJ per-hit error (skipping): %s", e)
                continue

        logger.info("WTTJ scrape_search complete: %d jobs", len(jobs))
        return jobs

    async def scrape_detail(self, url: str) -> Job:
        """Return minimal Job for a detail URL.

        All job data is already available from the Algolia search hit
        (title, company, description, salary, etc.). No second request
        is needed — this returns an empty Job so the pipeline enrichment
        step in _scrape_and_enrich is a no-op for WTTJ.

        Args:
            url: The job detail URL (ignored, data already collected).

        Returns:
            A Job with source and url set.
        """
        return Job(source=self.SOURCE, title="", url=url)

    # -- Internal helpers ----------------------------------------------------

    def _hit_to_job(
        self,
        hit: dict[str, Any],
        current_date: datetime,
        days_ago: int | None = None,
    ) -> Job | None:
        """Convert an Algolia hit to a Job, optionally filtering by age.

        Args:
            hit: A single hit from the Algolia response.
            current_date: Reference date for age filtering.
            days_ago: If set, skip jobs older than this many days.

        Returns:
            A Job object, or None if the hit is invalid or filtered out.
        """
        title = (hit.get("name") or "").strip()
        if not title:
            return None

        org = hit.get("organization", {}) or {}
        company = (org.get("name") or "").strip()

        # Build the job URL from org slug + job slug
        org_slug = (org.get("slug") or "").strip()
        job_slug = (hit.get("slug") or "").strip()
        if org_slug and job_slug:
            url = (
                f"https://www.welcometothejungle.com"
                f"/en/companies/{org_slug}/jobs/{job_slug}"
            )
        else:
            url = ""

        job = Job(
            source=self.SOURCE,
            title=title,
            url=url,
            company=company,
        )

        # Location from offices
        offices = hit.get("offices", [])
        if offices:
            first = offices[0]
            city = (first.get("city") or "").strip()
            country = (first.get("country") or "").strip()
            parts = [p for p in [city, country] if p]
            if parts:
                job.location = ", ".join(parts)

        # Salary
        salary_min = hit.get("salary_minimum")
        salary_max = hit.get("salary_maximum")
        salary_period = hit.get("salary_period") or ""
        if salary_min is not None or salary_max is not None:
            parts: list[str] = []
            if salary_min is not None:
                parts.append(f"{salary_min:,.0f} €".replace(",", "."))
            if salary_max is not None:
                parts.append(f"{salary_max:,.0f} €".replace(",", "."))
            salary_text = " - ".join(parts)
            period_label = _SALARY_PERIOD_LABEL.get(salary_period, salary_period)
            if period_label:
                salary_text += f" {period_label}"
            job.set_tag("salario", salary_text, 0.9)

        # Published date
        published_at = (hit.get("published_at") or "").strip()
        if published_at:
            job.set_tag("fecha_publicacion", published_at, 0.9)

            # Date filter: skip if older than days_ago
            if days_ago is not None:
                try:
                    pub = datetime.fromisoformat(published_at)
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=timezone.utc)
                    delta = (current_date - pub).days
                    if delta > days_ago:
                        return None
                except (ValueError, TypeError):
                    pass  # keep job if date parsing fails

        # Remote / modality
        contract_type = hit.get("contract_type", "")
        if contract_type:
            label = _REMOTE_LABEL.get(contract_type)
            if label:
                job.set_tag("modalidad", label, 0.9)

        # Description from key_missions
        key_missions = hit.get("key_missions", [])
        if key_missions:
            job.description = "\n".join(key_missions)

        # Contract type label
        contract_label = hit.get("contract_type_name")
        if contract_label:
            job.set_tag("tipo_contrato", contract_label, 0.9)

        return job


# Period label mapping for salary display
_SALARY_PERIOD_LABEL: dict[str, str] = {
    "yearly": "al año",
    "monthly": "al mes",
    "hourly": "por hora",
}

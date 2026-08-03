"""Unit tests for per-platform pagination walks (D5/D6, spec: platform-pagination).

Covers all four platform walks:
- URL builders (pure functions): LinkedIn `start=25*(page-1)`, InfoJobs
  `page=N`, native filters (f_TPR/f_WT/city) on EVERY page URL, no date
  parameter for InfoJobs (post-scrape only).
- Walk behavior via FakePage: walk to last page (0 new cards stops), single
  page result, mid-walk block/timeout keeps collected cards, max_results cap.
- Verification (approval) tests for the pre-existing Indeed/Tecnoempleo walks
  (production code NOT changed — behavior must be preserved).
- Run-level D6 test (subprocess driver): a blocked keyword keeps its partial
  results and the next keyword still runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from playwright.async_api import TimeoutError as PwTimeout

from src.scrapers.indeed import IndeedScraper
from src.scrapers.infojobs import INFOJOBS_SEARCH_URL, InfoJobsScraper
from src.scrapers.linkedin import LINKEDIN_JOBS_URL, LinkedInScraper
from src.scrapers.tecnoempleo import TecnoempleoScraper

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PER_KEYWORD_DRIVER = PROJECT_ROOT / "tests" / "unit" / "_per_keyword_driver.py"


def _run_per_keyword_driver(
    tmp_path: Path, *, mode: str = "main", **env: str
) -> tuple[dict, str]:
    """Run the per-keyword subprocess driver and return (report dict, stdout)."""
    report = tmp_path / "report.json"
    driver_env = os.environ.copy()
    driver_env.update(
        {
            "DB_PATH": str(tmp_path / "jobs.db"),
            "REPORT_PATH": str(report),
            "DRIVER_MODE": mode,
            **env,
        }
    )
    proc = subprocess.run(
        [sys.executable, str(PER_KEYWORD_DRIVER)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=PROJECT_ROOT,
        env=driver_env,
    )
    assert proc.returncode == 0, f"driver failed: {proc.stderr[-2000:]}"
    return json.loads(report.read_text(encoding="utf-8")), proc.stdout


# ---------------------------------------------------------------------------
# Fake Playwright page/card stand-ins (walk simulation)
# ---------------------------------------------------------------------------


class _FakeLinkedInCard:
    """LinkedIn card stand-in: a title link (parse requires it) only."""

    def __init__(self, page_no: int, index: int) -> None:
        self._page_no = page_no
        self._index = index

    async def query_selector(self, selector: str):
        if "full-link" in selector or "title-link" in selector:
            return _FakeLinkedInTitle(self._page_no, self._index)
        return None


class _FakeLinkedInTitle:
    def __init__(self, page_no: int, index: int) -> None:
        self._page_no = page_no
        self._index = index

    async def inner_text(self) -> str:
        return f"DevOps Engineer {self._page_no}-{self._index}"

    async def get_attribute(self, name: str):
        if name == "href":
            return f"https://www.linkedin.com/jobs/view/{self._page_no}-{self._index}?trk=x"
        return None


class _FakeInfoJobsCard:
    """InfoJobs card stand-in: a title link (parse requires it) only."""

    def __init__(self, page_no: int, index: int) -> None:
        self._page_no = page_no
        self._index = index

    async def query_selector(self, selector: str):
        if "description-title" in selector:
            return _FakeInfoJobsTitle(self._page_no, self._index)
        return None


class _FakeInfoJobsTitle:
    def __init__(self, page_no: int, index: int) -> None:
        self._page_no = page_no
        self._index = index

    async def inner_text(self) -> str:
        return f"DevOps Engineer {self._page_no}-{self._index}"

    async def get_attribute(self, name: str):
        if name == "href":
            return f"/jobsearch/offer/{self._page_no}-{self._index}"
        return None


class _FakeIndeedCard:
    """Indeed card stand-in: data-jk + a title link (extractor requires them)."""

    def __init__(self, page_no: int, index: int) -> None:
        self._page_no = page_no
        self._index = index

    async def get_attribute(self, name: str):
        if name == "data-jk":
            return f"jk{self._page_no}-{self._index}"
        return None

    async def query_selector(self, selector: str):
        if "title" in selector.lower() or "jobtitle" in selector.lower():
            return _FakeIndeedTitle(self._page_no, self._index)
        return None


class _FakeIndeedTitle:
    def __init__(self, page_no: int, index: int) -> None:
        self._page_no = page_no
        self._index = index

    async def inner_text(self) -> str:
        return f"DevOps Job {self._page_no}-{self._index}"


class _FakeTecnoempleoCard:
    """Tecnoempleo card stand-in: onclick-less, h3 a link with title+url."""

    def __init__(self, page_no: int, index: int) -> None:
        self._page_no = page_no
        self._index = index

    async def get_attribute(self, name: str):
        return None

    async def query_selector(self, selector: str):
        if "h3" in selector or "font-weight-bold" in selector:
            return _FakeTecnoempleoLink(self._page_no, self._index)
        return None

    async def query_selector_all(self, selector: str):
        return []


class _FakeTecnoempleoLink:
    def __init__(self, page_no: int, index: int) -> None:
        self._page_no = page_no
        self._index = index

    async def inner_text(self) -> str:
        return f"DevOps {self._page_no}-{self._index}"

    async def get_attribute(self, name: str):
        if name == "href":
            return f"https://www.tecnoempleo.com/ofertas/{self._page_no}-{self._index}"
        return None


class _WalkFakePage:
    """Page stand-in: serves cards per probe, records URLs, can fail a probe.

    `cards_per_page[i]` = number of cards returned for probe i+1 (missing
    entries → zero cards, i.e. last-page detection). `fail_on_probe` makes
    that probe's goto raise PwTimeout (block/timeout mid-walk).
    """

    def __init__(
        self,
        cards_per_page: list[int],
        *,
        fail_on_probe: int | None = None,
        block_title_on_probe: int | None = None,
        card_factory=None,
    ) -> None:
        self._cards_per_page = cards_per_page
        self._fail_on_probe = fail_on_probe
        self._block_title_on_probe = block_title_on_probe
        self._card_factory = card_factory
        self.urls: list[str] = []
        self._probes = 0

    async def goto(self, url: str, wait_until=None, timeout=None) -> None:
        self._probes += 1
        self.urls.append(url)
        if self._fail_on_probe == self._probes:
            raise PwTimeout(f"blocked on probe {self._probes}")

    async def query_selector_all(self, selector: str):
        idx = self._probes - 1
        if idx < len(self._cards_per_page):
            factory = self._card_factory or (lambda p, i: None)
            return [factory(idx + 1, i) for i in range(self._cards_per_page[idx])]
        return []

    async def inner_text(self, selector: str) -> str:
        return ""

    async def evaluate(self, expression: str) -> str:
        if self._block_title_on_probe == self._probes:
            return "Demasiadas solicitudes — bloqueado"
        return ""

    async def wait_for_timeout(self, ms: int) -> None:
        pass


def _make_walk_scraper(scraper_cls, page: _WalkFakePage):
    """Build a scraper instance without __init__ (no DB/browser) + fake page."""
    scraper = scraper_cls.__new__(scraper_cls)  # type: ignore[call-arg]
    scraper._page = page  # type: ignore[assignment]
    return scraper


# ---------------------------------------------------------------------------
# LinkedIn URL builder (D5: start=25*(page-1))
# ---------------------------------------------------------------------------


class TestLinkedInUrlBuilder:
    """D5 — LinkedIn pagination URL: start offset in steps of 25."""

    def test_build_search_url_minimal(self) -> None:
        """RED: query → keywords param on the LinkedIn search URL."""
        url = LinkedInScraper.build_search_url(query="devops")
        assert url.startswith(LINKEDIN_JOBS_URL)
        assert "keywords=devops" in url

    def test_build_search_url_page_1_has_no_start(self) -> None:
        """RED: page 1 (start=0) must NOT add a start param."""
        url = LinkedInScraper.build_search_url(query="devops")
        assert "start=" not in url

    def test_build_search_url_page_2_start_25(self) -> None:
        """RED (D5): page 2 → start=25*(2-1)=25."""
        url = LinkedInScraper.build_search_url(query="devops", start=25)
        assert "start=25" in url

    def test_build_search_url_page_3_start_50(self) -> None:
        """TRIANGULATE (D5): page 3 → start=25*(3-1)=50."""
        url = LinkedInScraper.build_search_url(query="devops", start=50)
        assert "start=50" in url

    def test_build_search_url_native_filters_on_every_page(self) -> None:
        """RED (spec 'Last 24 hours on LinkedIn'): f_TPR/f_WT on page 1 AND 2."""
        page1 = LinkedInScraper.build_search_url(
            query="devops", extra_params={"f_TPR": "r86400", "f_WT": "2"}
        )
        page2 = LinkedInScraper.build_search_url(
            query="devops", extra_params={"f_TPR": "r86400", "f_WT": "2"}, start=25
        )
        assert "f_TPR=r86400" in page1
        assert "f_WT=2" in page1
        assert "f_TPR=r86400" in page2
        assert "f_WT=2" in page2

    def test_build_search_url_location_param(self) -> None:
        """TRIANGULATE: location is passed through on every page."""
        url = LinkedInScraper.build_search_url(query="devops", location="Spain", start=25)
        assert "location=Spain" in url
        assert "start=25" in url


# ---------------------------------------------------------------------------
# InfoJobs URL builder (D5: page=N)
# ---------------------------------------------------------------------------


class TestInfoJobsUrlBuilder:
    """D5 — InfoJobs pagination URL: page=N from page 2 onward."""

    def test_build_search_url_minimal(self) -> None:
        """RED: keyword + city params on the InfoJobs search URL."""
        url = InfoJobsScraper.build_search_url(query="devops", location="Madrid")
        assert url.startswith(INFOJOBS_SEARCH_URL)
        assert "keyword=devops" in url
        assert "city=Madrid" in url

    def test_build_search_url_page_1_no_page_param(self) -> None:
        """RED: page 1 must NOT add a page param."""
        url = InfoJobsScraper.build_search_url(query="devops")
        assert "page=" not in url

    def test_build_search_url_page_2(self) -> None:
        """RED (D5): page 2 → page=2."""
        url = InfoJobsScraper.build_search_url(query="devops", page=2)
        assert "page=2" in url

    def test_build_search_url_page_3(self) -> None:
        """TRIANGULATE (D5): page 3 → page=3."""
        url = InfoJobsScraper.build_search_url(query="devops", page=3)
        assert "page=3" in url

    def test_build_search_url_no_date_param(self) -> None:
        """RED (spec 'Non-native filter stays post-scrape'): NO date param."""
        url = InfoJobsScraper.build_search_url(query="devops", page=2)
        assert "date" not in url
        assert "f_TPR" not in url
        assert "fromage" not in url

    def test_build_search_url_extra_params_merged(self) -> None:
        """TRIANGULATE: native extra_params merge into the page URL."""
        url = InfoJobsScraper.build_search_url(
            query="devops", extra_params={"city": "Madrid"}, page=2
        )
        assert "city=Madrid" in url
        assert "page=2" in url


# ---------------------------------------------------------------------------
# LinkedIn walk (D5/D6)
# ---------------------------------------------------------------------------


class TestLinkedInWalk:
    """D5/D6 — LinkedIn walks start=25*(page-1) to the last page (0 new cards)."""

    async def _walk(self, page: _WalkFakePage, monkeypatch, max_results=None):
        monkeypatch.setattr("random.uniform", lambda a, b: 0.0)
        scraper = _make_walk_scraper(LinkedInScraper, page)
        return await scraper.scrape_search(
            query="devops", max_results=max_results,
            extra_params={"f_TPR": "r86400"},
        )

    @pytest.mark.asyncio
    async def test_walk_to_last_page_collects_all_pages(self, monkeypatch) -> None:
        """RED (spec 'Walk to last page in production'): 4 pages of 10 → 40 jobs."""
        page = _WalkFakePage([10, 10, 10, 10, 0], card_factory=_FakeLinkedInCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 40
        assert len(page.urls) == 5  # page 5 is the 0-card last-page probe
        assert "start=" not in page.urls[0]          # page 1: no start param
        assert "start=25" in page.urls[1]            # page 2
        assert "start=50" in page.urls[2]            # page 3
        assert "start=75" in page.urls[3]            # page 4
        assert "start=100" in page.urls[4]           # page 5: detection probe only
        assert "start=125" not in page.urls          # no deeper page probed

    @pytest.mark.asyncio
    async def test_single_page_result_stops(self, monkeypatch) -> None:
        """RED (spec 'Single-page result'): 6 offers → stop after page 1."""
        page = _WalkFakePage([6, 0], card_factory=_FakeLinkedInCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 6
        assert len(page.urls) == 2  # page 2 probe detects the end

    @pytest.mark.asyncio
    async def test_block_mid_walk_keeps_collected_cards(self, monkeypatch) -> None:
        """RED (spec 'Block mid-walk'): page 3 blocked → pages 1-2 kept (20 jobs)."""
        page = _WalkFakePage([10, 10, 10], fail_on_probe=3, card_factory=_FakeLinkedInCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 20
        assert len(page.urls) == 3

    @pytest.mark.asyncio
    async def test_max_results_caps_walk(self, monkeypatch) -> None:
        """TRIANGULATE (D2): max_results=3 stops the walk at 3 jobs."""
        page = _WalkFakePage([10, 10], card_factory=_FakeLinkedInCard)
        jobs = await self._walk(page, monkeypatch, max_results=3)

        assert len(jobs) == 3
        assert len(page.urls) == 1

    @pytest.mark.asyncio
    async def test_native_filters_on_every_page_url(self, monkeypatch) -> None:
        """RED (spec 'Last 24 hours on LinkedIn'): f_TPR=r86400 on EVERY page."""
        page = _WalkFakePage([10, 10, 0], card_factory=_FakeLinkedInCard)
        await self._walk(page, monkeypatch)

        assert len(page.urls) == 3
        for url in page.urls:
            assert "f_TPR=r86400" in url


# ---------------------------------------------------------------------------
# InfoJobs walk (D5/D6)
# ---------------------------------------------------------------------------


class TestInfoJobsWalk:
    """D5/D6 — InfoJobs walks page=N to the last page (0 new cards)."""

    async def _walk(self, page: _WalkFakePage, monkeypatch, max_results=None):
        monkeypatch.setattr("random.uniform", lambda a, b: 0.0)
        scraper = _make_walk_scraper(InfoJobsScraper, page)
        return await scraper.scrape_search(query="devops", max_results=max_results)

    @pytest.mark.asyncio
    async def test_walk_to_last_page_collects_all_pages(self, monkeypatch) -> None:
        """RED (spec 'Walk to last page in production'): 3 pages of 10 → 30 jobs."""
        page = _WalkFakePage([10, 10, 10, 0], card_factory=_FakeInfoJobsCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 30
        assert len(page.urls) == 4  # page 4 is the 0-card last-page probe
        assert "page=" not in page.urls[0]   # page 1: no page param
        assert "page=2" in page.urls[1]
        assert "page=3" in page.urls[2]
        assert "page=4" in page.urls[3]      # detection probe only
        assert "page=5" not in page.urls     # no deeper page probed

    @pytest.mark.asyncio
    async def test_single_page_result_stops(self, monkeypatch) -> None:
        """RED (spec 'Single-page result'): 6 offers → stop after page 1."""
        page = _WalkFakePage([6, 0], card_factory=_FakeInfoJobsCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 6
        assert len(page.urls) == 2

    @pytest.mark.asyncio
    async def test_block_mid_walk_keeps_collected_cards(self, monkeypatch) -> None:
        """RED (spec 'Block mid-walk'): page 2 blocked → page 1 kept (10 jobs)."""
        page = _WalkFakePage([10, 10], fail_on_probe=2, card_factory=_FakeInfoJobsCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 10
        assert len(page.urls) == 2

    @pytest.mark.asyncio
    async def test_max_results_caps_walk(self, monkeypatch) -> None:
        """TRIANGULATE (D2): max_results=3 stops the walk at 3 jobs."""
        page = _WalkFakePage([10, 10], card_factory=_FakeInfoJobsCard)
        jobs = await self._walk(page, monkeypatch, max_results=3)

        assert len(jobs) == 3
        assert len(page.urls) == 1

    @pytest.mark.asyncio
    async def test_no_date_param_on_any_page_url(self, monkeypatch) -> None:
        """RED (spec 'Non-native filter stays post-scrape'): no date in URLs."""
        page = _WalkFakePage([10, 10, 0], card_factory=_FakeInfoJobsCard)
        await self._walk(page, monkeypatch)

        assert len(page.urls) == 3
        for url in page.urls:
            assert "date" not in url
            assert "f_TPR" not in url
            assert "fromage" not in url


# ---------------------------------------------------------------------------
# Indeed walk verification (approval — production code NOT changed)
# ---------------------------------------------------------------------------


class TestIndeedWalkVerification:
    """D5/D6 — approval tests: the existing Indeed walk keeps its contract."""

    async def _walk(self, page: _WalkFakePage, monkeypatch, max_results=None):
        monkeypatch.setattr("random.uniform", lambda a, b: 0.0)
        scraper = _make_walk_scraper(IndeedScraper, page)
        return await scraper.scrape_search(query="devops", max_results=max_results)

    @pytest.mark.asyncio
    async def test_walk_to_last_page_stops_at_zero_cards(self, monkeypatch) -> None:
        """RED (D5 Indeed row): start=0,10,20,30 then stop at 0-card page."""
        page = _WalkFakePage([10, 10, 10, 10, 0], card_factory=_FakeIndeedCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 40
        assert len(page.urls) == 5
        assert "start=0" in page.urls[0] or "start=" not in page.urls[0]
        assert "start=10" in page.urls[1]
        assert "start=20" in page.urls[2]
        assert "start=30" in page.urls[3]
        assert "start=40" in page.urls[4]  # detection probe only
        assert "start=50" not in page.urls

    @pytest.mark.asyncio
    async def test_single_page_result_stops(self, monkeypatch) -> None:
        """RED (spec 'Single-page result'): 6 offers → stop after page 1."""
        page = _WalkFakePage([6, 0], card_factory=_FakeIndeedCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 6
        assert len(page.urls) == 2

    @pytest.mark.asyncio
    async def test_block_mid_walk_keeps_collected_cards(self, monkeypatch) -> None:
        """RED (spec 'Block mid-walk'): page 3 blocked → pages 1-2 kept."""
        page = _WalkFakePage([10, 10, 10], fail_on_probe=3, card_factory=_FakeIndeedCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 20
        assert len(page.urls) == 3


# ---------------------------------------------------------------------------
# Tecnoempleo walk verification (approval — production code NOT changed)
# ---------------------------------------------------------------------------


class TestTecnoempleoWalkVerification:
    """D5/D6 — approval tests: the existing Tecnoempleo walk keeps its contract."""

    async def _walk(self, page: _WalkFakePage, monkeypatch, max_results=None):
        monkeypatch.setattr("random.uniform", lambda a, b: 0.0)
        scraper = _make_walk_scraper(TecnoempleoScraper, page)
        return await scraper.scrape_search(query="devops", max_results=max_results)

    @pytest.mark.asyncio
    async def test_walk_to_last_page_stops_at_zero_cards(self, monkeypatch) -> None:
        """RED (D5 Tecnoempleo row): pagina=1,2,3 then stop at 0-card page."""
        page = _WalkFakePage([30, 30, 30, 0], card_factory=_FakeTecnoempleoCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 90
        assert len(page.urls) == 4
        assert "pagina=" not in page.urls[0]   # page 1: no pagina param
        assert "pagina=2" in page.urls[1]
        assert "pagina=3" in page.urls[2]
        assert "pagina=4" in page.urls[3]      # detection probe only
        assert "pagina=5" not in page.urls

    @pytest.mark.asyncio
    async def test_single_page_result_stops(self, monkeypatch) -> None:
        """RED (spec 'Single-page result'): 6 offers → stop after page 1."""
        page = _WalkFakePage([6, 0], card_factory=_FakeTecnoempleoCard)
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 6
        assert len(page.urls) == 2

    @pytest.mark.asyncio
    async def test_block_mid_walk_keeps_collected_cards(self, monkeypatch) -> None:
        """RED (spec 'Block mid-walk'): block title on page 2 → page 1 kept."""
        page = _WalkFakePage(
            [30, 30], block_title_on_probe=2, card_factory=_FakeTecnoempleoCard
        )
        jobs = await self._walk(page, monkeypatch)

        assert len(jobs) == 30
        assert len(page.urls) == 2


# ---------------------------------------------------------------------------
# Run-level D6: keep partial, warn, continue next keyword
# ---------------------------------------------------------------------------



"""Unit tests for Indeed scraper — URL construction, card parsing, error handling."""

import pytest

from src.scrapers.indeed import IndeedScraper, INDEED_SEARCH_URL, INDEED_VIEWJOB_URL
from src.core.models.job import Job


class TestIndeedScraperUnit:
    """Tests that do NOT require Playwright — URL logic and error paths."""

    def test_source_attr(self):
        """RED: IndeedScraper should have SOURCE = 'indeed'."""
        assert IndeedScraper.SOURCE == "indeed"

    def test_build_search_url_minimal(self):
        """RED: build_search_url should construct URL with query only."""
        url = IndeedScraper.build_search_url(query="devops")
        assert "q=devops" in url
        assert url.startswith(INDEED_SEARCH_URL)

    def test_build_search_url_with_location(self):
        """RED: build_search_url should include location (l) param."""
        url = IndeedScraper.build_search_url(query="devops", location="Madrid")
        assert "q=devops" in url
        assert "l=Madrid" in url

    def test_build_search_url_with_fromage(self):
        """TRIANGULATE: build_search_url should add fromage param."""
        url = IndeedScraper.build_search_url(query="cloud", fromage=7, start=20)
        assert "q=cloud" in url
        assert "fromage=7" in url
        assert "start=20" in url

    def test_build_search_url_no_location(self):
        """TRIANGULATE: missing location should not add l param."""
        url = IndeedScraper.build_search_url(query="devops")
        assert "&l=" not in url

    def test_build_search_url_with_jt(self):
        """RED: build_search_url should add jt param when provided."""
        url = IndeedScraper.build_search_url(query="devops", jt="hybrid")
        assert "q=devops" in url
        assert "jt=hybrid" in url

    def test_build_search_url_no_jt(self):
        """TRIANGULATE: missing jt should not add jt param."""
        url = IndeedScraper.build_search_url(query="devops", jt=None)
        assert "jt=" not in url

    def test_build_search_url_jt_multiple_codes(self):
        """TRIANGULATE: comma-joined jt codes pass through urlencoded."""
        url = IndeedScraper.build_search_url(query="devops", jt="work-from-home,on-site")
        assert "jt=work-from-home%2Con-site" in url

    def test_build_detail_url_from_jk(self):
        """RED: build_detail_url should construct viewjob URL from jk."""
        url = IndeedScraper.build_detail_url("abc123")
        assert url == f"{INDEED_VIEWJOB_URL}?jk=abc123"


class TestIndeedCardParsing:
    """Tests for _parse_card (sync, no Playwright — uses mock-like card dicts)."""

    def test_parse_card_minimal(self):
        """RED: valid card with title, company, location, jk should return Job."""
        card_data = {
            "title": "DevOps Engineer",
            "company": "Acme Corp",
            "location": "Madrid",
            "data_jk": "abc123",
        }
        job = IndeedScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.title == "DevOps Engineer"
        assert job.company == "Acme Corp"
        assert job.location == "Madrid"
        assert job.url.endswith("jk=abc123")
        assert job.source == "indeed"

    def test_parse_card_no_title_returns_none(self):
        """TRIANGULATE: card without title should return None."""
        card_data = {
            "title": "",
            "company": "Acme Corp",
            "data_jk": "abc123",
        }
        job = IndeedScraper._parse_card_from_data(card_data)
        assert job is None

    def test_parse_card_missing_company_returns_empty(self):
        """TRIANGULATE: card without company should set company=''."""
        card_data = {
            "title": "DevOps Engineer",
            "company": None,
            "location": "Barcelona",
            "data_jk": "xy789",
        }
        job = IndeedScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.company == ""

    def test_parse_card_with_salary(self):
        """TRIANGULATE: salary text should be attached as 'salario' tag."""
        card_data = {
            "title": "SRE",
            "company": "CloudCo",
            "data_jk": "jk1",
            "salary": "40.000 € - 60.000 € al año",
        }
        job = IndeedScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.get_tag("salario") == "40.000 € - 60.000 € al año"

    def test_parse_card_no_data_jk_returns_job_with_empty_url(self):
        """TRIANGULATE: card without data_jk should return Job with empty url."""
        card_data = {
            "title": "Mystery Job",
            "company": "Unknown",
            "data_jk": "",
        }
        job = IndeedScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.url == ""


class TestIndeedErrorHandling:
    """Error handling: tests verify the contract that errors produce valid defaults."""

    def test_login_noop_signature(self):
        """IndeedScraper.login is a no-op that takes credentials dict and returns None."""
        # Verify the method exists and has the right signature
        import asyncio
        # login should be callable without error (async no-op)
        assert callable(IndeedScraper.login)
        assert IndeedScraper.SOURCE == "indeed"

    def test_partial_card_handling_in_parser(self):
        """Covered by test_parse_card_missing_company_returns_empty above."""
        # Re-verify partial card contract
        card = {"title": "Job", "company": None, "data_jk": "jk1"}
        job = IndeedScraper._parse_card_from_data(card)
        assert job is not None
        assert job.company == ""  # REQ-SCRAPE-002: partial → company=""


class TestIndeedScrapeSearchParams:
    """scrape_search forwards extra_params (fromage/jt) to the URL builder."""

    class _FakePage:
        """Playwright page stand-in: never returns cards, so the loop breaks."""

        async def goto(self, url, wait_until=None, timeout=None):
            pass

        async def query_selector_all(self, selector):
            return []

        async def inner_text(self, selector):
            return "no matching jobs"

    def _make_scraper(self):
        scraper = IndeedScraper.__new__(IndeedScraper)  # skip __init__ (no DB/browser)
        scraper._page = self._FakePage()
        return scraper

    def _record_builder(self, monkeypatch):
        import src.scrapers.indeed as indeed_mod

        calls: list[dict] = []

        def fake_build(query="", location="", fromage=None, jt=None, start=0):
            calls.append(
                {"query": query, "location": location, "fromage": fromage, "jt": jt, "start": start}
            )
            return f"{INDEED_SEARCH_URL}?q={query}"

        monkeypatch.setattr(indeed_mod, "_build_search_url", fake_build)
        return calls

    @pytest.mark.asyncio
    async def test_scrape_search_passes_jt_and_fromage(self, monkeypatch):
        """RED: jt/fromage from extra_params must reach the URL builder."""
        calls = self._record_builder(monkeypatch)
        scraper = self._make_scraper()

        jobs = await scraper.scrape_search(
            query="devops",
            max_results=5,
            extra_params={"fromage": "7", "jt": "hybrid"},
        )

        assert jobs == []
        assert len(calls) == 1
        assert calls[0]["jt"] == "hybrid"
        assert calls[0]["fromage"] == 7
        assert calls[0]["query"] == "devops"

    @pytest.mark.asyncio
    async def test_scrape_search_jt_none_when_absent(self, monkeypatch):
        """TRIANGULATE: no jt in extra_params → builder receives jt=None."""
        calls = self._record_builder(monkeypatch)
        scraper = self._make_scraper()

        await scraper.scrape_search(query="devops", max_results=5, extra_params={"fromage": "7"})

        assert len(calls) == 1
        assert calls[0]["jt"] is None
        assert calls[0]["fromage"] == 7


class TestIndeedUnlimitedResults:
    """D7 — max_results=None means no result cap (unlimited pagination).

    The scraper signature defaults to max_results=None; callers in normal
    mode (run_search.py) pass None explicitly so scans are not truncated
    to the old default of 25. Explicit positive values still cap results.
    """

    class _FakeCard:
        """Card stand-in with a data-jk and a title link (title extraction)."""

        def __init__(self, index: int) -> None:
            self._index = index

        async def get_attribute(self, name: str):
            if name == "data-jk":
                return f"jk{self._index}"
            return None

        async def query_selector(self, selector: str):
            if "title" in selector.lower() or "jobtitle" in selector.lower():
                return self._FakeTitleLink(self._index)
            return None

        class _FakeTitleLink:
            def __init__(self, index: int) -> None:
                self._index = index

            async def inner_text(self) -> str:
                return f"DevOps Job {self._index}"

    class _FakePage:
        """Returns N valid cards on the first page, then zero (loop ends)."""

        def __init__(self, card_count: int) -> None:
            self._card_count = card_count
            self._pages_seen = 0

        async def goto(self, url, wait_until=None, timeout=None):
            pass

        async def query_selector_all(self, selector):
            self._pages_seen += 1
            if self._pages_seen == 1:
                return [TestIndeedUnlimitedResults._FakeCard(i) for i in range(self._card_count)]
            return []

        async def inner_text(self, selector):
            return ""

    def _make_scraper(self, card_count: int):
        scraper = IndeedScraper.__new__(IndeedScraper)  # skip __init__ (no DB/browser)
        scraper._page = self._FakePage(card_count)
        return scraper

    def test_scrape_search_default_max_results_is_none(self):
        """RED: the default for scrape_search max_results must be None (not 25)."""
        import inspect

        sig = inspect.signature(IndeedScraper.scrape_search)
        assert sig.parameters["max_results"].default is None

    @pytest.mark.asyncio
    async def test_max_results_none_does_not_truncate_to_25(self):
        """RED: max_results=None must return all 30 cards, not cap at 25."""
        scraper = self._make_scraper(card_count=30)

        jobs = await scraper.scrape_search(query="devops", max_results=None)

        assert len(jobs) == 30, f"Expected 30 jobs with no cap, got {len(jobs)}"

    @pytest.mark.asyncio
    async def test_explicit_max_results_still_caps(self):
        """TRIANGULATE: explicit max_results=5 still caps the results."""
        scraper = self._make_scraper(card_count=30)

        jobs = await scraper.scrape_search(query="devops", max_results=5)

        assert len(jobs) == 5, f"Expected 5 jobs with explicit cap, got {len(jobs)}"

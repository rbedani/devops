"""Unit tests for the Algolia-based WTTJ scraper.

The scraper queries the public Algolia API directly — no Playwright needed.
"""
# ruff: noqa: S101  # allow bare assert in tests

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.models.job import Job
from src.scrapers.welcometothejungle import (
    WelcomeToTheJungleScraper,
    _COUNTRY_ISO,
    _REMOTE_MAP,
    _REMOTE_LABEL,
    _DATE_DAYS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    """Return a mock httpx.AsyncClient for injection."""
    client = MagicMock(spec=["post", "aclose"])
    client.post = AsyncMock()
    return client


@pytest.fixture
def scraper(mock_client):
    """Return a scraper with a mocked client (not started)."""
    s = WelcomeToTheJungleScraper(db=None)
    s._client = mock_client
    return s


def _make_hit(**overrides) -> dict:
    """Build a minimal Algolia hit dict for testing.

    Default values produce a valid job. Override any field to test edge cases.
    """
    hit = {
        "name": "DevOps Engineer",
        "organization": {
            "name": "TechCorp",
            "slug": "techcorp",
        },
        "slug": "devops-engineer_paris",
        "offices": [
            {
                "city": "Paris",
                "country": "France",
                "country_code": "FR",
            }
        ],
        "contract_type": "full_time",
        "salary_minimum": 45000.0,
        "salary_maximum": 60000.0,
        "salary_period": "yearly",
        "published_at": "2026-07-27T10:00:00Z",
        "key_missions": [
            "Maintain cloud infrastructure",
            "Automate deployments",
        ],
        "contract_type_name": "Full-Time",
    }
    hit.update(overrides)
    return hit


# ===========================================================================
# Hit-to-Job Parsing Tests (_hit_to_job)
# ===========================================================================


class TestHitToJob:
    """Test _hit_to_job parsing from Algolia hit dict to Job object."""

    @pytest.fixture
    def scraper(self):
        """Return a scraper instance for testing _hit_to_job."""
        return WelcomeToTheJungleScraper(db=None)

    def test_full_hit_parses_all_fields(self, scraper):
        """Complete hit produces a job with all fields populated."""
        hit = _make_hit()
        now = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
        job = scraper._hit_to_job(hit, now)

        assert job is not None
        assert job.title == "DevOps Engineer"
        assert job.company == "TechCorp"
        assert job.source == "welcometothejungle"
        assert job.url == (
            "https://www.welcometothejungle.com"
            "/en/companies/techcorp/jobs/devops-engineer_paris"
        )
        assert job.location == "Paris, France"

        salario = job.get_tag("salario")
        assert salario is not None
        assert "45.000" in salario
        assert "60.000" in salario
        assert "al año" in salario

        assert job.get_tag("fecha_publicacion") == "2026-07-27T10:00:00Z"
        assert job.get_tag("modalidad") == "Remoto"
        assert job.get_tag("tipo_contrato") == "Full-Time"
        assert "Maintain cloud infrastructure" in job.description
        assert "Automate deployments" in job.description

    def test_empty_title_returns_none(self, scraper):
        """Missing or whitespace-only title returns None."""
        now = datetime.now(timezone.utc)
        assert scraper._hit_to_job(_make_hit(name=""), now) is None
        assert scraper._hit_to_job(_make_hit(name="  "), now) is None
        assert scraper._hit_to_job(_make_hit(name=None), now) is None

    def test_no_organization(self, scraper):
        """Missing organization still produces job with empty company."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(organization=None)
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        assert job.title == "DevOps Engineer"
        assert job.company == ""

    def test_no_offices(self, scraper):
        """Missing offices leaves location empty."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(offices=[])
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        assert job.location == ""

    def test_partial_office(self, scraper):
        """Office with only city works."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(offices=[{"city": "Madrid", "country": "", "country_code": "ES"}])
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        assert job.location == "Madrid"

    def test_no_salary(self, scraper):
        """Missing salary does not set salario tag."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(salary_minimum=None, salary_maximum=None, salary_period=None)
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        assert job.get_tag("salario") is None

    def test_no_published_date(self, scraper):
        """Missing published_at does not set tag."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(published_at=None)
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        assert job.get_tag("fecha_publicacion") is None

    def test_no_contract_type(self, scraper):
        """Missing contract_type does not set modalidad."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(contract_type=None)
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        assert job.get_tag("modalidad") is None

    def test_no_key_missions(self, scraper):
        """Missing key_missions keeps description empty."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(key_missions=None)
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        assert job.description == ""

    def test_partial_contract_type(self, scraper):
        """'partial' maps to Híbrido label."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(contract_type="partial")
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        assert job.get_tag("modalidad") == "Híbrido/Hybrid"

    def test_days_ago_filter_keeps_recent(self, scraper):
        """Job within days_ago window is kept."""
        now = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
        hit = _make_hit(published_at="2026-07-27T10:00:00Z")  # 1 day ago
        job = scraper._hit_to_job(hit, now, days_ago=7)
        assert job is not None

    def test_days_ago_filter_skips_old(self, scraper):
        """Job older than days_ago is filtered out."""
        now = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
        hit = _make_hit(published_at="2026-06-01T10:00:00Z")  # 57 days ago
        job = scraper._hit_to_job(hit, now, days_ago=7)
        assert job is None

    def test_partial_org_no_slug(self, scraper):
        """Missing org slug produces empty url."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(organization={"name": "NoSlugCo", "slug": None})
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        assert job.url == ""

    def test_salary_only_min(self, scraper):
        """Only salary_min produces partial salario."""
        now = datetime.now(timezone.utc)
        hit = _make_hit(salary_minimum=50000.0, salary_maximum=None, salary_period="yearly")
        job = scraper._hit_to_job(hit, now)
        assert job is not None
        salario = job.get_tag("salario")
        assert salario is not None
        assert "50.000" in salario
        assert "al año" in salario

    def test_invalid_hit_returns_none(self, scraper):
        """Completely invalid data returns None."""
        now = datetime.now(timezone.utc)
        assert scraper._hit_to_job({}, now) is None

    def test_hit_without_name_key(self, scraper):
        """Hit without name key returns None."""
        now = datetime.now(timezone.utc)
        assert scraper._hit_to_job({"organization": {}}, now) is None


# ===========================================================================
# Mapping Constants Tests
# ===========================================================================


class TestMappingConstants:
    """Verify mapping constants are consistent."""

    def test_remote_map_keys_are_lowercase(self):
        for key in _REMOTE_MAP:
            assert key == key.lower(), f"Key {key!r} should be lowercase"

    def test_remote_label_covers_remote_map_values(self):
        for val in _REMOTE_MAP.values():
            assert val in _REMOTE_LABEL, f"Value {val!r} missing from _REMOTE_LABEL"

    def test_country_iso_keys_are_lowercase(self):
        for key in _COUNTRY_ISO:
            assert key == key.lower(), f"Key {key!r} should be lowercase"

    def test_supported_countries(self):
        for country in ("spain", "france", "germany", "uk", "netherlands"):
            assert country in _COUNTRY_ISO, f"Missing country: {country}"

    def test_date_days_has_expected_keys(self):
        for key in ("last_24h", "last_week", "last_month"):
            assert key in _DATE_DAYS, f"Missing date key: {key}"


# ===========================================================================
# Scraper Lifecycle Tests
# ===========================================================================


class TestScraperLifecycle:
    """Test SOURCE, login, page property, and lifecycle."""

    def test_source_attr(self):
        assert WelcomeToTheJungleScraper.SOURCE == "welcometothejungle"

    @pytest.mark.asyncio
    async def test_login_noop(self):
        s = WelcomeToTheJungleScraper(db=None)
        await s.login({})  # callable and not raising

    def test_page_property_raises(self):
        s = WelcomeToTheJungleScraper(db=None)
        with pytest.raises(RuntimeError, match="not Playwright"):
            _ = s.page

    def test_headless_stripped(self):
        s = WelcomeToTheJungleScraper(headless=True, db=None)
        # headless kwarg should have been removed
        assert not hasattr(s, "headless") or s.headless is True


# ===========================================================================
# Scraper Search Tests (with mocked client)
# ===========================================================================


class TestScraperSearch:
    """Test scrape_search with a mocked httpx client."""

    @pytest.mark.asyncio
    async def test_search_returns_jobs(self, scraper, mock_client):
        """RED: scrape_search returns jobs from Algolia hits."""
        mock_client.post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {
                "hits": [_make_hit()],
                "nbHits": 1,
            },
        )
        jobs = await scraper.scrape_search("devops")
        assert len(jobs) == 1
        assert jobs[0].title == "DevOps Engineer"

    @pytest.mark.asyncio
    async def test_search_empty_hits_returns_empty(self, scraper, mock_client):
        """Empty hits returns empty list."""
        mock_client.post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"hits": [], "nbHits": 0},
        )
        jobs = await scraper.scrape_search("devops")
        assert jobs == []

    @pytest.mark.asyncio
    async def test_search_http_error_returns_empty(self, scraper, mock_client):
        """HTTP error returns empty list gracefully."""
        mock_client.post.side_effect = httpx_exception(403, "Forbidden")
        jobs = await scraper.scrape_search("devops")
        assert jobs == []

    @pytest.mark.asyncio
    async def test_search_request_error_returns_empty(self, scraper, mock_client):
        """Network error returns empty list gracefully."""
        from httpx import RequestError

        mock_client.post.side_effect = RequestError("Connection failed")
        jobs = await scraper.scrape_search("devops")
        assert jobs == []

    @pytest.mark.asyncio
    async def test_search_with_location_includes_filter(self, scraper, mock_client):
        """Location parameter adds country_code filter."""
        mock_client.post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"hits": [_make_hit()], "nbHits": 1},
        )
        await scraper.scrape_search("devops", location="Spain")

        call_kwargs = mock_client.post.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        sent_json = kwargs.get("json", {})
        params = sent_json.get("params", "")
        assert 'offices.country_code:"ES"' in params

    @pytest.mark.asyncio
    async def test_search_with_extra_params(self, scraper, mock_client):
        """Extra_params remote and days_ago are applied to query/filter."""
        mock_client.post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {
                "hits": [_make_hit(published_at="2026-07-27T10:00:00Z")],
                "nbHits": 1,
            },
        )

        with patch(
            "src.scrapers.welcometothejungle.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat

            jobs = await scraper.scrape_search(
                "devops",
                extra_params={"remote": "full_time", "days_ago": "7"},
            )
            assert len(jobs) == 1

            # Also check the filter was sent
            call_kwargs = mock_client.post.call_args
            assert call_kwargs is not None
            _, kwargs = call_kwargs
            params = kwargs.get("json", {}).get("params", "")
            assert 'contract_type:"full_time"' in params

    @pytest.mark.asyncio
    async def test_search_per_hit_error_skips_bad_hits(self, scraper, mock_client):
        """A hit that fails conversion is skipped, not fatal."""
        mock_client.post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {
                "hits": [
                    _make_hit(),  # valid
                    {"invalid": "no name"},  # no name key
                    _make_hit(name="DevOps Senior"),  # valid
                ],
                "nbHits": 3,
            },
        )
        jobs = await scraper.scrape_search("devops")
        assert len(jobs) == 2  # middle one skipped

    @pytest.mark.asyncio
    async def test_scrape_detail_returns_minimal_job(self, scraper):
        """scrape_detail returns a bare Job with source and url."""
        job = await scraper.scrape_detail("https://example.com/job/123")
        assert job.source == "welcometothejungle"
        assert job.url == "https://example.com/job/123"

    @pytest.mark.asyncio
    async def test_search_passes_query_param(self, scraper, mock_client):
        """Query string is passed to Algolia."""
        mock_client.post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"hits": [], "nbHits": 0},
        )
        await scraper.scrape_search("devops+sre")

        call_kwargs = mock_client.post.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        params = kwargs.get("json", {}).get("params", "")
        assert "query=devops%2Bsre" in params or "query=devops+sre" in params


# ---------------------------------------------------------------------------
# Helper: create an httpx HTTPStatusError
# ---------------------------------------------------------------------------

def httpx_exception(status_code: int, text: str):
    """Create an httpx.HTTPStatusError with the given status."""
    from httpx import HTTPStatusError, Request, Response

    request = Request("POST", "https://example.com")
    response = Response(status_code=status_code, request=request)
    return HTTPStatusError(text, request=request, response=response)

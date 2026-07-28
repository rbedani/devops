"""Unit tests for Tecnoempleo scraper — URL construction, card parsing, error handling.

Following Strict TDD and the Indeed patterns: SOURCE, build_search_url,
_parse_card_from_data, degradation, error paths.
"""

import pytest

from src.core.models.job import Job


# ---------------------------------------------------------------------------
# Import the module-level functions once the module exists.
# For RED state, we import from the to-be-created module.
# ---------------------------------------------------------------------------

TECNOEMPLEO_SEARCH_URL = "https://www.tecnoempleo.com/ofertas-trabajo"


class TestTecnoempleoScraperUnit:
    """Tests that do NOT require Playwright — URL logic and error paths."""

    @pytest.fixture(autouse=True)
    def _ensure_module(self):
        """Ensure the module is importable (triggers ImportError if missing in RED)."""
        import src.scrapers.tecnoempleo  # noqa: F401

    def test_source_attr(self):
        """RED: TecnoempleoScraper should have SOURCE = 'tecnoempleo'."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        assert TecnoempleoScraper.SOURCE == "tecnoempleo"

    # -- URL builder tests ---------------------------------------------------

    def test_build_search_url_minimal(self):
        """RED: build_search_url with only keyword should produce path-segment URL."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        url = TecnoempleoScraper.build_search_url(query="devops")
        assert "/ofertas-trabajo/devops" in url
        assert url.startswith(TECNOEMPLEO_SEARCH_URL)

    def test_build_search_url_with_keyword_spaces(self):
        """RED: multi-word keyword should be hyphen-joined in URL path."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        url = TecnoempleoScraper.build_search_url(query="devops cloud")
        assert "/ofertas-trabajo/devops-cloud" in url

    def test_build_search_url_with_page(self):
        """RED: page > 1 should add ?pagina=N param."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        url = TecnoempleoScraper.build_search_url(query="devops", page=2)
        assert "?pagina=2" in url
        assert "/ofertas-trabajo/devops" in url

    def test_build_search_url_page_1_no_param(self):
        """TRIANGULATE: page=1 should NOT add ?pagina= param."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        url = TecnoempleoScraper.build_search_url(query="devops", page=1)
        assert "?pagina=" not in url

    def test_build_search_url_with_remote(self):
        """RED: en_remoto=True should add query param."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        url = TecnoempleoScraper.build_search_url(query="devops", en_remoto=True)
        assert "?en_remoto=,1," in url

    def test_build_search_url_with_location(self):
        """RED: location should be embedded in path before keyword."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        url = TecnoempleoScraper.build_search_url(query="devops", location="madrid")
        assert "/ofertas-trabajo/madrid/devops" in url

    def test_build_search_url_combined(self):
        """TRIANGULATE: all params combined: location + keyword + page + remote."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        url = TecnoempleoScraper.build_search_url(
            query="devops cloud", location="madrid", page=3, en_remoto=True
        )
        assert "/ofertas-trabajo/madrid/devops-cloud" in url
        assert "?pagina=3" in url
        assert "en_remoto=,1," in url


class TestTecnoempleoCardParsing:
    """Tests for _parse_card_from_data (sync, no Playwright — uses dicts)."""

    @pytest.fixture(autouse=True)
    def _ensure_module(self):
        import src.scrapers.tecnoempleo  # noqa: F401

    def test_parse_card_full_fields(self):
        """RED: valid card with all fields should return complete Job."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": "DevOps Engineer",
            "company": "Acme Corp",
            "location": "Madrid",
            "url": "https://www.tecnoempleo.com/devops-engineer-acme/rf-abc123",
            "date": "28/07/2026",
            "salary": "36.000\u20ac - 42.000\u20ac b/a",
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.title == "DevOps Engineer"
        assert job.company == "Acme Corp"
        assert job.location == "Madrid"
        assert job.url == "https://www.tecnoempleo.com/devops-engineer-acme/rf-abc123"
        assert job.source == "tecnoempleo"
        assert job.get_tag("salario") == "36.000\u20ac - 42.000\u20ac b/a"
        assert job.get_tag("fecha_publicacion") == "28/07/2026"

    def test_parse_card_minimal(self):
        """RED: card with only title and url should still produce Job."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": "DevOps",
            "url": "https://www.tecnoempleo.com/devops/rf-xyz",
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.title == "DevOps"
        assert job.company == ""
        assert job.location == ""
        assert job.source == "tecnoempleo"

    def test_parse_card_no_title_returns_none(self):
        """TRIANGULATE: card without title should return None."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": "",
            "company": "Acme",
            "url": "https://example.com/job",
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is None

    def test_parse_card_missing_optionals(self):
        """TRIANGULATE: missing salary, date, company should produce valid Job with empty fields."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": "SRE",
            "url": "https://www.tecnoempleo.com/sre/rf-1",
            "location": "",
            "company": None,
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.company == ""
        assert job.get_tag("salario") is None
        assert job.get_tag("fecha_publicacion") is None

    def test_parse_card_modality_from_location(self):
        """RED: location containing modality e.g. 'Madrid (Hibrido)' should set tag."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": "Cloud Engineer",
            "url": "https://www.tecnoempleo.com/cloud/rf-2",
            "location": "Madrid (H\u00edbrido)",
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.get_tag("modalidad") == "H\u00edbrido"

    def test_parse_card_location_without_modality(self):
        """TRIANGULATE: location without parentheses should have no modality tag."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": "Engineer",
            "url": "https://www.tecnoempleo.com/eng/rf-3",
            "location": "Barcelona",
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.get_tag("modalidad") is None

    def test_parse_card_remote_location(self):
        """TRIANGULATE: '100% remoto' as location should set remotomodality."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": "Remote DevOps",
            "url": "https://www.tecnoempleo.com/remote/rf-4",
            "location": "100% remoto",
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.get_tag("modalidad") == "100% remoto"

    def test_parse_card_tech_tags(self):
        """RED: tech_tags list should be attached as 'tecnologias' tag."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": "DevOps",
            "url": "https://www.tecnoempleo.com/devops/rf-5",
            "tech_tags": ["Docker", "Kubernetes", "AWS"],
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is not None
        assert job.get_tag("tecnologias") == "Docker, Kubernetes, AWS"


class TestTecnoempleoErrorHandling:
    """Error handling: tests verify the contract that errors produce valid defaults."""

    @pytest.fixture(autouse=True)
    def _ensure_module(self):
        import src.scrapers.tecnoempleo  # noqa: F401

    def test_login_noop_signature(self):
        """TecnoempleoScraper.login is a no-op that takes credentials dict."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        assert callable(TecnoempleoScraper.login)
        assert TecnoempleoScraper.SOURCE == "tecnoempleo"

    def test_parse_card_edge_case_none_title(self):
        """TRIANGULATE: None title should return None."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": None,
            "url": "https://example.com/job",
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is None

    def test_parse_card_whitespace_title(self):
        """TRIANGULATE: whitespace-only title should return None."""
        from src.scrapers.tecnoempleo import TecnoempleoScraper
        card_data = {
            "title": "   ",
            "url": "https://example.com/job",
        }
        job = TecnoempleoScraper._parse_card_from_data(card_data)
        assert job is None
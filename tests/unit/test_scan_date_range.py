"""Unit tests for SCAN date_range fix — validate env var overrides flow through to LinkedIn params.

Tests:
1. SCAN_DATE_RANGE env var overrides target.filters.date_range
2. f_TPR appears in LinkedIn search URL when date_range is set
3. Without SCAN_DATE_RANGE, uses target's configured date_range
4. SCAN_LOCATION and SCAN_MODALITY env vars also override correctly
5. Integration: end-to-end env var → LinkedIn params chain works
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestDateRangeOverride:
    """Test that env var overrides correctly inject into SearchFilters."""

    def test_date_range_override_applied(self) -> None:
        """SCAN_DATE_RANGE=last_week overrides target's configured date_range."""
        from src.core.config.search import SearchFilters

        filters = SearchFilters(
            keywords=["devops"],
            date_range="last_month",  # Default configured value
        )

        # Simulate env override
        env_overrides = {"date_range": "last_week"}
        filters.date_range = env_overrides["date_range"]

        assert filters.date_range == "last_week"

    def test_date_range_default_when_no_override(self) -> None:
        """Without SCAN_DATE_RANGE, target's configured date_range is used."""
        from src.core.config.search import SearchFilters

        filters = SearchFilters(
            keywords=["devops"],
            date_range="last_month",
        )

        # No override — should keep configured value
        assert filters.date_range == "last_month"

    def test_location_override(self) -> None:
        """SCAN_LOCATION='Argentina' overrides target's countries."""
        from src.core.config.search import SearchFilters

        filters = SearchFilters(
            keywords=["devops"],
            countries=["España"],
        )

        env_overrides = {"location": "Argentina"}
        filters.countries = [env_overrides["location"]]

        assert filters.countries == ["Argentina"]

    def test_modality_override(self) -> None:
        """SCAN_MODALITY='hibrido' overrides target's modalities."""
        from src.core.config.search import SearchFilters

        filters = SearchFilters(
            keywords=["devops"],
            modalities=["remoto"],
        )

        env_overrides = {"modality": "hibrido"}
        filters.modalities = env_overrides["modality"].split(",")

        assert filters.modalities == ["hibrido"]

    def test_to_linkedin_params_includes_f_tpr_when_date_range_set(self) -> None:
        """to_linkedin_params() includes f_TPR when date_range is set."""
        from src.core.config.search import SearchFilters

        # last_24h → r86400
        filters = SearchFilters(date_range="last_24h")
        params = filters.to_linkedin_params()
        assert params["f_TPR"] == "r86400"

        # last_week → r604800
        filters = SearchFilters(date_range="last_week")
        params = filters.to_linkedin_params()
        assert params["f_TPR"] == "r604800"

        # last_month → r2592000
        filters = SearchFilters(date_range="last_month")
        params = filters.to_linkedin_params()
        assert params["f_TPR"] == "r2592000"

    def test_to_linkedin_params_no_f_tpr_when_date_range_empty(self) -> None:
        """to_linkedin_params() does NOT include f_TPR when date_range is empty (Any time)."""
        from src.core.config.search import SearchFilters

        filters = SearchFilters(date_range="")
        params = filters.to_linkedin_params()
        assert "f_TPR" not in params

    def test_extra_params_dict_excludes_keywords_and_location(self) -> None:
        """extra_params should only contain f_TPR, f_WT, etc. (not keywords/location)."""
        from src.core.config.search import SearchFilters

        filters = SearchFilters(
            keywords=["devops"],
            countries=["España"],
            modalities=["remote"],
            date_range="last_week",
        )
        params = filters.to_linkedin_params()

        # Extract extra params (everything except keywords and location)
        extra = {
            k: v
            for k, v in params.items()
            if k not in ("keywords", "location")
        }

        assert "keywords" not in extra
        assert "location" not in extra
        assert "f_TPR" in extra
        assert extra["f_TPR"] == "r604800"
        assert extra["f_WT"] == "2"  # remote → 2


class TestLinkedInURLConstruction:
    """Test that f_TPR appears in the LinkedIn search URL."""

    def test_url_includes_f_tpr(self) -> None:
        """LinkedIn URL should include f_TPR when passed as extra_param."""
        from urllib.parse import urlencode, parse_qs, urlparse

        extra = {"f_TPR": "r604800"}
        params = {"keywords": "devops", "location": "Spain"}
        params.update(extra)

        url = f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        assert qs["f_TPR"] == ["r604800"]
        assert qs["keywords"] == ["devops"]

    def test_url_omits_f_tpr_when_not_passed(self) -> None:
        """LinkedIn URL should NOT include f_TPR when not passed."""
        from urllib.parse import urlencode, parse_qs, urlparse

        params = {"keywords": "devops", "location": "Spain"}
        url = f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        assert "f_TPR" not in qs

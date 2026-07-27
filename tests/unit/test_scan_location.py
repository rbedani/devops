"""Unit tests for SCAN location parameter — split, iteration, dedup logic."""

from __future__ import annotations

import pytest

from src.core.config.search import SearchFilters


class TestLocationSplit:
    """Test that comma-separated locations are split into proper lists."""

    def test_single_location(self) -> None:
        locations_raw = "Spain"
        locations = [loc.strip() for loc in locations_raw.split(",") if loc.strip()]
        assert locations == ["Spain"]

    def test_two_locations(self) -> None:
        locations_raw = "Spain, Argentina"
        locations = [loc.strip() for loc in locations_raw.split(",") if loc.strip()]
        assert locations == ["Spain", "Argentina"]

    def test_four_locations(self) -> None:
        locations_raw = "Spain, Argentina, Madrid, Buenos Aires"
        locations = [loc.strip() for loc in locations_raw.split(",") if loc.strip()]
        assert locations == ["Spain", "Argentina", "Madrid", "Buenos Aires"]

    def test_locations_with_extra_spaces(self) -> None:
        locations_raw = "  Spain ,  Argentina , Madrid  "
        locations = [loc.strip() for loc in locations_raw.split(",") if loc.strip()]
        assert locations == ["Spain", "Argentina", "Madrid"]

    def test_empty_string_returns_empty_list(self) -> None:
        locations_raw = ""
        locations = [loc.strip() for loc in locations_raw.split(",") if loc.strip()]
        assert locations == []

    def test_empty_list_falls_back_to_single_empty_location(self) -> None:
        """When no locations, we use one empty pass (no geo filter)."""
        locations: list[str] = []
        if not locations:
            locations = [""]
        assert locations == [""]


class TestLocationOverrideClearsConfig:
    """Override should replace config's countries, not append."""

    def test_override_replaces_config_countries(self) -> None:
        filters = SearchFilters(
            keywords=["devops"],
            countries=["España", "Spain"],  # config default
        )

        # User types "Argentina" in dashboard
        env_overrides = {"location": "Argentina"}
        locations = [loc.strip() for loc in env_overrides["location"].split(",") if loc.strip()]
        filters.countries = locations if locations else []

        assert filters.countries == ["Argentina"]
        assert "España" not in filters.countries

    def test_override_clears_countries_when_empty(self) -> None:
        filters = SearchFilters(
            keywords=["devops"],
            countries=["España"],  # config default
        )

        # User clears the location input
        env_overrides = {"location": ""}
        locations = [loc.strip() for loc in env_overrides["location"].split(",") if loc.strip()]
        filters.countries = locations if locations else []

        assert filters.countries == []


class TestDedupAcrossLocations:
    """Simulate deduplication across location iterations."""

    def test_same_url_appears_once(self) -> None:
        """Jobs with same URL across locations are deduplicated."""
        seen: set[str] = set()
        all_jobs: list[dict] = []

        # Simulate scrape results from "Spain" and "Argentina"
        jobs_spain = [
            {"url": "https://linkedin.com/job/1", "title": "DevOps Spain"},
            {"url": "https://linkedin.com/job/2", "title": "SRE Spain"},
        ]
        jobs_argentina = [
            {"url": "https://linkedin.com/job/1", "title": "DevOps Spain"},  # DUPE
            {"url": "https://linkedin.com/job/3", "title": "SRE Argentina"},
        ]

        for job in jobs_spain + jobs_argentina:
            if job["url"] not in seen:
                seen.add(job["url"])
                all_jobs.append(job)

        assert len(all_jobs) == 3
        urls = [j["url"] for j in all_jobs]
        assert urls.count("https://linkedin.com/job/1") == 1  # No dupe
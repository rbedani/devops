"""Unit tests for modular search configuration."""

import json
import pytest
from pathlib import Path

from src.config.search import SearchFilters, SearchTarget, load_targets, save_targets


class TestSearchFilters:
    def test_linkedin_params_keywords(self):
        f = SearchFilters(keywords=["devops", "ansible"])
        params = f.to_linkedin_params()
        assert params["keywords"] == "devops ansible"

    def test_linkedin_params_location(self):
        f = SearchFilters(countries=["España"])
        params = f.to_linkedin_params()
        assert params["location"] == "España"

    def test_linkedin_params_date_last_week(self):
        f = SearchFilters(date_range="last_week")
        params = f.to_linkedin_params()
        assert params["f_TPR"] == "r604800"

    def test_linkedin_params_modality_remote(self):
        f = SearchFilters(modalities=["remoto"])
        params = f.to_linkedin_params()
        assert params["f_WT"] == "2"

    def test_linkedin_params_modality_multiple(self):
        f = SearchFilters(modalities=["remoto", "hibrido"])
        params = f.to_linkedin_params()
        assert "2" in params["f_WT"]
        assert "1" in params["f_WT"]

    def test_matches_job_no_filter_passes_all(self):
        f = SearchFilters()
        assert f.matches_job(type("Job", (), {"get_tag": lambda self, k: None})())

    def test_matches_job_with_matching_modality(self):
        f = SearchFilters(modalities=["remoto"])
        job = type("Job", (), {"get_tag": lambda self, k: "Remoto" if k == "modalidad" else None})()
        assert f.matches_job(job)

    def test_matches_job_with_non_matching_modality(self):
        f = SearchFilters(modalities=["remoto"])
        job = type("Job", (), {"get_tag": lambda self, k: "Presencial" if k == "modalidad" else None})()
        assert not f.matches_job(job)


class TestSearchTarget:
    def test_create_target(self):
        t = SearchTarget(
            name="devops_españa",
            platform="linkedin",
            filters=SearchFilters(keywords=["devops"], countries=["España"]),
        )
        assert t.name == "devops_españa"
        assert t.platform == "linkedin"

    def test_serialization_roundtrip(self):
        t = SearchTarget(
            name="test",
            platform="linkedin",
            filters=SearchFilters(keywords=["devops"], countries=["España"], date_range="last_week"),
        )
        json_str = t.to_json()
        t2 = SearchTarget.from_json(json_str)
        assert t2.name == "test"
        assert t2.filters.keywords == ["devops"]
        assert t2.filters.date_range == "last_week"

    def test_save_and_load(self, tmp_path: Path):
        t = SearchTarget(
            name="save_test",
            platform="linkedin",
            filters=SearchFilters(keywords=["ansible"]),
        )
        path = tmp_path / "target.json"
        t.save(path)
        t2 = SearchTarget.load(path)
        assert t2.name == "save_test"
        assert t2.filters.keywords == ["ansible"]

    def test_batch_save_load(self, tmp_path: Path):
        targets = [
            SearchTarget(name="t1", platform="linkedin", filters=SearchFilters(keywords=["devops"])),
            SearchTarget(name="t2", platform="linkedin", filters=SearchFilters(keywords=["ansible"])),
        ]
        path = tmp_path / "targets.json"
        save_targets(targets, path)
        loaded = load_targets(path)
        assert len(loaded) == 2
        assert loaded[0].name == "t1"
        assert loaded[1].name == "t2"

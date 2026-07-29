"""Unit tests for modular search configuration."""

import json
import pytest
from pathlib import Path

from src.core.config.search import SearchFilters, SearchTarget, load_targets, save_targets


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

    # -- Indeed params (T-002) -------------------------------------------------

    def test_indeed_params_keywords(self):
        """RED: keywords should map to q (space-joined)."""
        f = SearchFilters(keywords=["devops", "cloud"])
        params = f.to_indeed_params()
        assert params["q"] == "devops cloud"

    def test_indeed_params_location(self):
        """RED: countries should map to l (comma-joined)."""
        f = SearchFilters(countries=["Madrid", "Barcelona"])
        params = f.to_indeed_params()
        assert params["l"] == "Madrid, Barcelona"

    def test_indeed_params_date_last_24h(self):
        """RED: last_24h → fromage=1."""
        f = SearchFilters(date_range="last_24h")
        params = f.to_indeed_params()
        assert params["fromage"] == "1"

    def test_indeed_params_date_last_week(self):
        """RED: last_week → fromage=7."""
        f = SearchFilters(date_range="last_week")
        params = f.to_indeed_params()
        assert params["fromage"] == "7"

    def test_indeed_params_date_last_month(self):
        """TRIANGULATE: last_month → fromage=30."""
        f = SearchFilters(date_range="last_month")
        params = f.to_indeed_params()
        assert params["fromage"] == "30"

    def test_indeed_params_empty_filters(self):
        """TRIANGULATE: empty filters should return {}."""
        f = SearchFilters()
        params = f.to_indeed_params()
        assert params == {}

    def test_indeed_params_modality_remoto(self):
        """RED: remoto → jt=work-from-home."""
        f = SearchFilters(modalities=["remoto"])
        params = f.to_indeed_params()
        assert params["jt"] == "work-from-home"

    def test_indeed_params_modality_presencial(self):
        """TRIANGULATE: presencial → jt=on-site."""
        f = SearchFilters(modalities=["presencial"])
        params = f.to_indeed_params()
        assert params["jt"] == "on-site"

    def test_indeed_params_modality_unknown_skipped(self):
        """TRIANGULATE: unknown modality should be skipped silently."""
        f = SearchFilters(modalities=["hibrido", "desconocido"])
        params = f.to_indeed_params()
        assert "jt" not in params

    # -- Tecnoempleo params (TECNO-001) ---------------------------------------

    def test_tecnoempleo_params_keyword_join(self):
        """RED: keywords should map to 'keyword' (space-joined) for path-slug."""
        f = SearchFilters(keywords=["devops", "cloud"])
        params = f.to_tecnoempleo_params()
        assert params["keyword"] == "devops cloud"

    def test_tecnoempleo_params_en_remoto(self):
        """RED: 'remoto' modality should produce en_remoto=',1,'."""
        f = SearchFilters(modalities=["remoto"])
        params = f.to_tecnoempleo_params()
        assert "en_remoto" in params
        assert params["en_remoto"] == ",1,"

    def test_tecnoempleo_params_passthrough(self):
        """RED: location and date_range should pass through as metadata."""
        f = SearchFilters(countries=["Madrid"], date_range="last_week")
        params = f.to_tecnoempleo_params()
        assert params["location"] == "Madrid"
        assert params["date_range"] == "last_week"

    def test_tecnoempleo_params_empty_filters(self):
        """TRIANGULATE: empty filters should return empty dict."""
        f = SearchFilters()
        params = f.to_tecnoempleo_params()
        assert params == {}

    def test_tecnoempleo_params_modality_multiple(self):
        """TRIANGULATE: 'hibrido' without 'remoto' should NOT set en_remoto."""
        f = SearchFilters(modalities=["hibrido", "presencial"])
        params = f.to_tecnoempleo_params()
        assert "en_remoto" not in params

    def test_tecnoempleo_params_keywords_single(self):
        """TRIANGULATE: single keyword should still be in params as-is."""
        f = SearchFilters(keywords=["devops"])
        params = f.to_tecnoempleo_params()
        assert params["keyword"] == "devops"


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

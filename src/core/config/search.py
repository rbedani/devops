"""Modular search configuration for job scraping.

Every search is defined as a SearchTarget: a platform + filters.
Targets are serializable (JSON/YAML) so users can configure
searches without touching code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class SearchFilters:
    """All possible filters for a job search."""

    keywords: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    date_range: str = ""          # e.g. "last_week", "last_month", "2026-07-01:2026-07-24"
    salary_min: str = ""
    salary_max: str = ""
    exclude_keywords: list[str] = field(default_factory=list)
    language: str = ""            # e.g. "es", "en"

    def to_linkedin_params(self) -> dict[str, str]:
        """Convert filters to LinkedIn search URL parameters."""
        params: dict[str, str] = {}

        if self.keywords:
            params["keywords"] = " ".join(self.keywords)

        if self.countries:
            params["location"] = ", ".join(self.countries)

        # LinkedIn date filter codes
        date_map = {
            "last_24h": "r86400",
            "last_week": "r604800",
            "last_month": "r2592000",
        }
        if self.date_range and self.date_range in date_map:
            params["f_TPR"] = date_map[self.date_range]

        # Modality filter (LinkedIn uses f_WT for work type)
        mod_map = {
            "remoto": "2",      # Remote
            "remote": "2",
            "hibrido": "1",     # Hybrid
            "hybrid": "1",
            "presencial": "3",  # On-site
            "onsite": "3",
        }
        if self.modalities:
            codes = [mod_map[m.lower()] for m in self.modalities if m.lower() in mod_map]
            if codes:
                params["f_WT"] = ",".join(codes)

        return params

    def to_infojobs_params(self) -> dict[str, str]:
        """Convert filters to InfoJobs search URL parameters.

        InfoJobs does not support modality or date-range filters via URL
        parameters. Modality filtering is handled post-scrape by matches_job().
        """
        params: dict[str, str] = {}

        if self.keywords:
            params["keyword"] = " ".join(self.keywords)

        # InfoJobs uses city facet for location
        if self.countries:
            params["city"] = ", ".join(self.countries)

        return params

    def to_indeed_params(self) -> dict[str, str]:
        """Convert filters to Indeed search URL parameters."""
        params: dict[str, str] = {}

        if self.keywords:
            params["q"] = " ".join(self.keywords)

        if self.countries:
            params["l"] = ", ".join(self.countries)

        # Indeed date filter codes (fromage parameter in days)
        date_map = {
            "last_24h": "1",
            "last_week": "7",
            "last_month": "30",
        }
        if self.date_range and self.date_range in date_map:
            params["fromage"] = date_map[self.date_range]

        # Modality filter (best-effort; silently skip unknown values)
        mod_map = {
            "remoto": "work-from-home",
            "remote": "work-from-home",
            "presencial": "on-site",
            "onsite": "on-site",
        }
        if self.modalities:
            codes = [mod_map[m.lower()] for m in self.modalities if m.lower() in mod_map]
            if codes:
                params["jt"] = ",".join(codes)

        return params

    def to_tecnoempleo_params(self) -> dict[str, str]:
        """Convert filters to Tecnoempleo search parameters.

        Tecnoempleo uses path-segment URLs for keywords, query param for
        remote modality, and metadata passthrough for location/date_range.
        """
        params: dict[str, str] = {}

        if self.keywords:
            params["keyword"] = " ".join(self.keywords)

        # Remote modality → en_remoto=,1,
        if self.modalities:
            if any(m.lower() in ("remoto", "remote") for m in self.modalities):
                params["en_remoto"] = ",1,"

        if self.countries:
            params["location"] = ", ".join(self.countries)

        if self.date_range:
            params["date_range"] = self.date_range

        return params

    def to_wttj_params(self) -> dict[str, str]:
        """Convert filters to Welcome to the Jungle search URL parameters.

        WTTJ uses Algolia refinement filters for location (ISO code),
        remote modality (contract_types), and date range (days_ago).
        """
        params: dict[str, str] = {}

        if self.keywords:
            params["keyword"] = " ".join(self.keywords)

        # WTTJ remote modality → Algolia contract_type facet
        wttj_remote_map = {
            "remoto": "full_time",
            "remote": "full_time",
            "hibrido": "partial",
            "hybrid": "partial",
            "presencial": "full_time",
            "onsite": "full_time",
        }
        if self.modalities:
            for m in self.modalities:
                val = wttj_remote_map.get(m.lower())
                if val:
                    params["remote"] = val
                    break

        # WTTJ date range → days_ago (post-filtered by scraper)
        wttj_date_days = {
            "last_24h": "1",
            "last_week": "7",
            "last_month": "30",
        }
        if self.date_range and self.date_range in wttj_date_days:
            params["days_ago"] = wttj_date_days[self.date_range]

        return params

    def matches_job(self, job: Any) -> bool:
        """Check if a scraped job matches this filter set.

        Uses modality synonym groups so that target "remoto" also matches
        job modalities like "Teletrabajo", "Solo teletrabajo", or "Work from home".
        """
        if not self.modalities:
            return True

        job_modality = (job.get_tag("modalidad") or "").lower()
        if job_modality:
            for m in self.modalities:
                synonyms = _MODALITY_SYNONYMS.get(m.lower(), [m.lower()])
                for syn in synonyms:
                    if syn in job_modality:
                        return True
            return False

        # If no modality tag, don't filter out
        return True


# Modality synonym groups (mirrors _detect_modality in src/tags/detector.py).
# Each group maps canonical filter terms to their synonym sets.
_MODALITY_SYNONYMS: dict[str, list[str]] = {
    "remoto": ["remoto", "remote", "teletrabajo", "work from home", "wfh", "from home"],
    "remote": ["remoto", "remote", "teletrabajo", "work from home", "wfh", "from home"],
    "hibrido": ["híbrido", "hibrido", "hybrid", "semi-presencial", "híbrida"],
    "híbrido": ["híbrido", "hibrido", "hybrid", "semi-presencial", "híbrida"],
    "hybrid": ["híbrido", "hibrido", "hybrid", "semi-presencial", "híbrida"],
    "presencial": ["presencial", "on-site", "onsite", "in office", "en oficina"],
    "onsite": ["presencial", "on-site", "onsite", "in office", "en oficina"],
    "on-site": ["presencial", "on-site", "onsite", "in office", "en oficina"],
}


@dataclass
class SearchTarget:
    """A complete search definition: platform + filters + limits."""

    name: str                              # human label e.g. "devops_españa"
    platform: str                          # e.g. "linkedin", "indeed", "computrabajo"
    filters: SearchFilters = field(default_factory=SearchFilters)
    max_results: int = 25
    enabled: bool = True
    tags: list[str] = field(default_factory=list)  # freeform tags for grouping

    # -- Serialisation ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchTarget:
        filters_data = data.pop("filters", {})
        return cls(
            filters=SearchFilters(**filters_data),
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__},
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> SearchTarget:
        return cls.from_dict(json.loads(text))

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> SearchTarget:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def __repr__(self) -> str:
        kw = ", ".join(self.filters.keywords)
        loc = ", ".join(self.filters.countries)
        return f"SearchTarget({self.name!r}, {self.platform}, kw=[{kw}], loc=[{loc}])"


# ---------------------------------------------------------------------------
# Batch loader
# ---------------------------------------------------------------------------

def load_targets(path: Path | str) -> list[SearchTarget]:
    """Load multiple SearchTargets from a JSON file (array of target dicts)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [SearchTarget.from_dict(t) for t in data]


def save_targets(targets: list[SearchTarget], path: Path | str) -> None:
    """Save multiple SearchTargets to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = [t.to_dict() for t in targets]
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
"""Pure helpers for SCAN UI env-var overrides.

Kept free of subprocess/side effects so unit tests can exercise the whole
override contract (SCAN-KW-01..06) without launching run_search.py.
"""

from __future__ import annotations

from src.core.config.search import SearchTarget
from src.core.models.job import Job
from src.scan.matcher import matches_relevance


def split_keywords(raw: str) -> list[str]:
    """Split a raw keyword input into a cleaned keyword list.

    Comma-separated; strips surrounding whitespace; drops empty parts
    ("devops,,sre" -> ["devops", "sre"]). Preserves accents and internal
    spaces ("platform engineer"). Truncation happens earlier, in
    sanitize_keyword (runner.py), before this split.
    """
    return [part.strip() for part in raw.split(",") if part.strip()]


def apply_env_overrides(target: SearchTarget, env_overrides: dict[str, str]) -> None:
    """Apply dashboard env-var overrides to a target's filters, in place.

    Presence-based: a key overrides the configured filter whenever it is
    present, even with an empty value (empty = explicit "no filter").
    Unknown keys are ignored. Covers keywords (SCAN-KW-01/02), location,
    modality, date_range, and salary_min/salary_max (SCAN-SAL) — the full
    SCAN override surface.
    """
    if "keywords" in env_overrides:
        target.filters.keywords = split_keywords(env_overrides["keywords"])
    if "date_range" in env_overrides:
        target.filters.date_range = env_overrides["date_range"]
    if "location" in env_overrides:
        # Split comma-separated locations into a proper list
        # "Spain, Argentina, Madrid" -> ["Spain", "Argentina", "Madrid"]
        locations = [loc.strip() for loc in env_overrides["location"].split(",") if loc.strip()]
        target.filters.countries = locations if locations else []
    if "modality" in env_overrides:
        # Empty string = explicit "no filter" (clear modalities)
        if env_overrides["modality"]:
            target.filters.modalities = env_overrides["modality"].split(",")
        else:
            target.filters.modalities = []
    if "salary_min" in env_overrides:
        # Presence-based: raw value travels untouched; empty = no filter.
        # The parser in search.py is the single normaliser (D4).
        target.filters.salary_min = env_overrides["salary_min"]
    if "salary_max" in env_overrides:
        target.filters.salary_max = env_overrides["salary_max"]


def matches_any_keyword(job: Job, keywords: list[str]) -> bool:
    """Return True when any keyword matches the job title, company or description.

    Thin delegation to the token-aware relevance matcher (matcher.py) so the
    SCAN keyword gate and the dashboard share one implementation (spec:
    job-relevance-matcher). Matching is case-insensitive, token-aware and
    synonym-expanded; an empty keyword list matches everything (no filter).
    """
    return matches_relevance(job, keywords)

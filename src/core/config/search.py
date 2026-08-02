"""Modular search configuration for job scraping.

Every search is defined as a SearchTarget: a platform + filters.
Targets are serializable (JSON/YAML) so users can configure
searches without touching code.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
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
            "hibrido": "hybrid",
            "hybrid": "hybrid",
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
        if self.modalities:  # noqa: SIM102
            if any(m.lower() in ("remoto", "remote") for m in self.modalities):
                params["en_remoto"] = ",1,"

        if self.countries:
            params["location"] = ", ".join(self.countries)

        if self.date_range:
            params["date_range"] = self.date_range

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

    def matches_date_range(self, job: Any) -> bool:
        """Check if the job's publication date falls within date_range.

        Conservative by design: unknown ranges, missing tags, and unparseable
        dates always pass — a job is never silently excluded on bad data.
        Relative cutoffs (last_24h/last_week/last_month) are inclusive.
        Custom ranges use "A:B" with inclusive bounds (naive UTC).
        """
        if not self.date_range:
            return True
        if self.date_range not in _DATE_RANGE_CUTOFFS and ":" not in self.date_range:
            return True

        now = datetime.now(UTC).replace(tzinfo=None)
        parsed = _parse_fecha_publicacion(job.get_tag("fecha_publicacion") or "", now=now)
        if parsed is None:
            return True

        if self.date_range in _DATE_RANGE_CUTOFFS:
            return parsed >= now - _DATE_RANGE_CUTOFFS[self.date_range]

        # Custom "A:B" range — inclusive bounds (naive UTC)
        start_raw, _, end_raw = self.date_range.partition(":")
        start = _parse_fecha_publicacion(start_raw.strip(), now=now)
        end = _parse_fecha_publicacion(end_raw.strip(), now=now)
        if start is None or end is None:
            return True
        return start <= parsed <= end

    def matches_salary(self, job: Any) -> bool:
        """Check if the job's salary falls within the requested range.

        Inclusive bounds (D2): a job range [job_min, job_max] passes when
        job_max >= filter_min AND job_min <= filter_max. Filter bounds are
        normalised by _parse_salary (a single-value filter like "30k" acts
        as both min and max). When the filter bounds are inverted
        (min > max) BOTH are ignored and every job passes — the UI shows a
        warning but the backend is authoritative (D5). Conservative by
        design: jobs without a salary tag or with unparseable salary text
        always pass (never silently excluded on bad data).
        """
        if not self.salary_min and not self.salary_max:
            return True

        min_range = _parse_salary(self.salary_min) if self.salary_min else None
        max_range = _parse_salary(self.salary_max) if self.salary_max else None
        # Unparseable filter bound → no restriction (same rule as the job
        # side): the bound is ignored, never crashes and never filters.
        min_bound: int | None = min_range[0] if min_range is not None else None
        max_bound: int | None = max_range[0] if max_range is not None else None

        # Inverted bounds → ignore both filters (D5)
        if min_bound is not None and max_bound is not None and min_bound > max_bound:
            return True

        job_range = _parse_salary(job.get_tag("salario") or "")
        if job_range is None:
            return True

        job_min, job_max = job_range
        if min_bound is not None and job_max < min_bound:
            return False
        return not (max_bound is not None and job_min > max_bound)


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

# Relative date-range cutoffs (inclusive: parsed == cutoff passes).
_DATE_RANGE_CUTOFFS: dict[str, timedelta] = {
    "last_24h": timedelta(hours=24),
    "last_week": timedelta(days=7),
    "last_month": timedelta(days=30),
}

_MONTHS: dict[str, int] = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

_RELATIVE_RE = re.compile(r"^(?:hace\s+)?(\d+)\s*([dhm])\s*$")
_NUMERIC_DATE_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")
_MONTH_DATE_RE = re.compile(r"^(\d{1,2})\s+([a-záéíóúñ]+)$")

_RELATIVE_DELTAS = {
    "d": timedelta(days=1),
    "h": timedelta(hours=1),
    "m": timedelta(minutes=1),
}


def _parse_fecha_publicacion(value: str, now: datetime | None = None) -> datetime | None:
    """Parse a publication-date string into a naive UTC datetime.

    Formats tried in order:
      - ISO 8601 ("2026-07-24T10:30:00Z", "2026-07-24") → naive UTC
      - Relative Spanish ("Hace 2d", "5h", "30m") → now - delta
      - Numeric ("24/07/2026", "24-07-2026") → midnight
      - "D mon" ("5 jul") → midnight, year inferred from now (future → previous)

    Returns None when the value cannot be parsed; callers treat that as
    "no date filter applied" (conservative).
    """
    if now is None:
        now = datetime.now(UTC).replace(tzinfo=None)
    value = value.strip().lower()
    if not value:
        return None

    # 1. ISO 8601 — Z means UTC; aware datetimes are converted to UTC
    try:
        parsed = datetime.fromisoformat(value.replace("z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed

    # 2. Relative "Hace Nd/Nh/Nm" or short "Nd/Nh/Nm"
    m = _RELATIVE_RE.match(value)
    if m:
        amount = int(m.group(1))
        return now - amount * _RELATIVE_DELTAS[m.group(2)]

    # 3. Numeric DD/MM/YYYY or DD-MM-YYYY
    m = _NUMERIC_DATE_RE.match(value)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None

    # 4. "D mon" — Spanish month abbreviation, year inferred from now
    m = _MONTH_DATE_RE.match(value)
    if m:
        day = int(m.group(1))
        month = _MONTHS.get(m.group(2))
        if month is None:
            return None
        year = now.year
        if (month, day) > (now.month, now.day):
            year -= 1
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    return None


def _parse_salary(value: str) -> tuple[int, int] | None:
    """Parse raw salary text into an inclusive (min, max) EUR tuple (D1).

    Understands:
      - k-suffix: "30k" → 30000 (treated as single value → (30000, 30000))
      - plain number: "30000" → 30000
      - ES thousand dots: "30.000" → 30000
      - € suffix: "30000€" → 30000
      - full range: "€36.000 - €42.000 b/a" → (36000, 42000)
      - single value "30k" → (30000, 30000) — D2: min == max

    Returns None when the text contains no numbers (no salary info).
    """
    if not value or not value.strip():
        return None

    # Normalise separators: unify dash variants, strip currency symbols
    text = value.replace("–", "-").replace("—", "-").replace("€", "")
    text = text.replace(".", "").replace(",", ".").lower().strip()

    # k-suffix: multiply by 1000
    if re.search(r"\d\s*k\b", text):
        text = re.sub(r"(\d+(?:\.\d+)?)\s*k\b", lambda m: str(int(float(m.group(1)) * 1000)), text)

    # Extract all numbers; the range bounds are min/max of them (inclusive)
    numbers = [int(round(float(m))) for m in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    return (min(numbers), max(numbers))


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
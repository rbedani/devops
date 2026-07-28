"""Tag auto-detection engine."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.core.models.job import JobTag


@dataclass
class TagDetector:
    """A single tag extraction rule."""

    key: str
    extract_fn: Callable[[str, str, dict[str, Any]], list[tuple[str, float]]]
    description: str = ""
    priority: int = 0

    def detect(self, title: str, description: str, metadata: dict[str, Any]) -> list[JobTag]:
        raw = self.extract_fn(title, description, metadata)
        return [JobTag(key=self.key, value=val, confidence=conf) for val, conf in raw]


class TagRegistry:
    """Registry of tag detectors."""

    def __init__(self) -> None:
        self._detectors: list[TagDetector] = []

    def register(
        self,
        key: str,
        extract_fn: Callable[[str, str, dict[str, Any]], list[tuple[str, float]]],
        description: str = "",
        priority: int = 0,
    ) -> None:
        det = TagDetector(key=key, extract_fn=extract_fn, description=description, priority=priority)
        self._detectors.append(det)
        self._detectors.sort(key=lambda d: -d.priority)

    def detect_all(self, title: str, description: str, metadata: dict[str, Any]) -> list[JobTag]:
        tags: list[JobTag] = []
        seen_keys: set[str] = set()
        for det in self._detectors:
            found = det.detect(title, description, metadata)
            for tag in found:
                if tag.key not in seen_keys:
                    tags.append(tag)
                    seen_keys.add(tag.key)
        return tags

    @property
    def registered_keys(self) -> list[str]:
        return [d.key for d in self._detectors]

    def __len__(self) -> int:
        return len(self._detectors)


# ---------------------------------------------------------------------------
# Built-in detectors
# ---------------------------------------------------------------------------

def _detect_modality(title: str, description: str, _meta: dict[str, Any]) -> list[tuple[str, float]]:
    text = f"{title} {description}".lower()
    patterns: list[tuple[str, float]] = []

    remote_kw = ["remoto", "remote", "teletrabajo", "work from home", "wfh", "from home"]
    hybrid_kw = ["híbrido", "hibrido", "hybrid", "semi-presencial", "híbrida"]
    onsite_kw = ["presencial", "on-site", "onsite", "in office", "en oficina"]

    for kw in remote_kw:
        if kw in text:
            patterns.append(("Remoto", 0.9))
            break
    for kw in hybrid_kw:
        if kw in text:
            patterns.append(("Híbrido", 0.85))
            break
    for kw in onsite_kw:
        if kw in text:
            patterns.append(("Presencial", 0.85))
            break

    return patterns


def _detect_schedule(title: str, description: str, _meta: dict[str, Any]) -> list[tuple[str, float]]:
    text = f"{title} {description}".lower()
    patterns: list[tuple[str, float]] = []

    full_kw = ["full-time", "full time", "tiempo completo", "jornada completa"]
    part_kw = ["part-time", "part time", "medio tiempo", "media jornada"]
    contract_kw = ["contrato", "contract", "freelance", "independiente"]

    for kw in full_kw:
        if kw in text:
            patterns.append(("Tiempo completo", 0.85))
            break
    for kw in part_kw:
        if kw in text:
            patterns.append(("Medio tiempo", 0.85))
            break
    for kw in contract_kw:
        if kw in text:
            patterns.append(("Contrato", 0.7))
            break

    return patterns


def _parse_first_number(raw: str) -> float | None:
    """Extract and parse the FIRST number from a salary string.

    Handles ranges like "$80,000 - $100,000" by parsing only "$80,000".
    """
    # Remove currency symbols
    cleaned = raw.replace("€", "").replace("$", "").replace("USD", "").replace("EUR", "").strip()

    # Take only up to the first separator (-, –, a, to)
    cleaned = re.split(r'\s*[-–aA]\s*', cleaned)[0].strip()

    # Handle k/K/mil suffix
    multiplier = 1
    k_match = re.search(r'(\d+)\s*k\b', cleaned, re.IGNORECASE)
    if k_match:
        cleaned = k_match.group(1)
        multiplier = 1000
    elif "mil" in cleaned.lower():
        cleaned = re.sub(r'\s*mil\s*', '', cleaned, flags=re.IGNORECASE)
        multiplier = 1000

    # Remove everything except digits and dots/commas
    cleaned = re.sub(r'[^\d.,]', '', cleaned)

    # European format: "45.000" → 45000
    if re.match(r'^\d{1,3}\.\d{3}$', cleaned):
        cleaned = cleaned.replace(".", "")
    # European decimal: "45.000,50" → 45000.50
    elif re.match(r'^\d{1,3}\.\d{3},\d+$', cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    # US thousands: "45,000" → 45000
    elif re.match(r'^\d{1,3},\d{3}', cleaned):
        cleaned = cleaned.replace(",", "")

    try:
        return float(cleaned) * multiplier
    except (ValueError, TypeError):
        return None


def _is_likely_salary(value: float) -> bool:
    """Check if a numeric value is in a reasonable annual salary range (EUR)."""
    return 15_000 <= value <= 500_000


def _is_year_like(text: str) -> bool:
    """Check if the matched text contains a year (2000-2099)."""
    for num in re.findall(r'\d{4}', text):
        if 2000 <= int(num) <= 2099:
            return True
    return False


def _detect_salary(title: str, description: str, _meta: dict[str, Any]) -> list[tuple[str, float]]:
    """Detect salary in EUR/USD with validation against false positives."""
    text = f"{title} {description}"
    patterns: list[tuple[str, float]] = []
    seen: set[str] = set()

    # Currency symbols
    CURR = r'(?:USD?\s*|\$\s*|€\s*|S/\s*|ARS\s*|CLP\s*|COP\s*)'
    CURR_ANY = r'(?:€|USD|EUR|\$)?'
    NUM = r'\d[\d.,]*\s*(?:k|K|mil)?'
    SEP = r'(?:\s*[-–aA]\s*)'

    # --- Pattern 1: Salary keyword + amount ---
    KW = r'(?:salario|salary|compensaci[oó]n|remuneraci[oó]n|pay|remuneration|sueldo|compensa|rango\s+salarial|salary\s+range)'
    kw_re = re.compile(
        KW + r'[:\s]*'
        + CURR + r'?' + NUM + CURR_ANY
        + r'(?:' + SEP + CURR + r'?' + NUM + CURR_ANY + r')?',
        re.IGNORECASE,
    )
    for m in kw_re.finditer(text):
        val = m.group(0).strip()
        if val in seen or _is_year_like(val):
            continue
        parsed = _parse_first_number(val)
        if parsed is not None and not _is_likely_salary(parsed):
            continue
        patterns.append((val, 0.95))
        seen.add(val)

    # --- Pattern 2: Currency + number (no keyword needed) ---
    curr_re = re.compile(
        CURR + r'?' + NUM + CURR_ANY
        + r'(?:' + SEP + CURR + r'?' + NUM + CURR_ANY + r')?',
        re.IGNORECASE,
    )
    for m in curr_re.finditer(text):
        val = m.group(0).strip()
        if len(val) < 4 or val in seen or _is_year_like(val):
            continue
        if not any(c.isdigit() for c in val):
            continue
        # Must contain a currency symbol
        if not re.search(r'[€$]', val) and not re.search(r'\b(USD|EUR)\b', val, re.IGNORECASE):
            continue
        parsed = _parse_first_number(val)
        if parsed is not None and not _is_likely_salary(parsed):
            continue
        patterns.append((val, 0.8))
        seen.add(val)

    # --- Pattern 3: Attach "bruto anual" context ---
    bruto_re = re.compile(r'(?:bruto|gross)\s*(?:anual|yearly|per\s+year|annual)?', re.IGNORECASE)
    for m in bruto_re.finditer(text):
        if patterns:
            last_val = patterns[-1][0]
            patterns[-1] = (f"{last_val} bruto anual", 0.9)

    return patterns


def _detect_vacancies(title: str, description: str, _meta: dict[str, Any]) -> list[tuple[str, float]]:
    text = f"{title} {description}".lower()
    patterns: list[tuple[str, float]] = []

    vac_re = re.compile(r'(\d+)\s*(?:vacante|puesto|position|opening|available)')
    for m in vac_re.finditer(text):
        patterns.append((m.group(1), 0.9))

    return patterns


def _detect_applicants(title: str, description: str, meta: dict[str, Any]) -> list[tuple[str, float]]:
    patterns: list[tuple[str, float]] = []

    if "applicants" in meta:
        val = str(meta["applicants"])
        patterns.append((val, 1.0))
        return patterns

    text = f"{title} {description}"
    app_re = re.compile(
        r'(\d[\d,.]*)\s*(?:applicant|postulante|persona|people\s+applied|candidatos?)',
        re.IGNORECASE,
    )
    for m in app_re.finditer(text):
        patterns.append((m.group(1), 0.8))

    return patterns


def _detect_publication_date(title: str, description: str, meta: dict[str, Any]) -> list[tuple[str, float]]:
    patterns: list[tuple[str, float]] = []

    if "published_date" in meta:
        patterns.append((str(meta["published_date"]), 1.0))
        return patterns

    text = f"{title} {description}".lower()
    date_re = re.compile(
        r'(\d{1,2}\s+(?:de\s+)?(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\w*\.?\s*(?:de\s+)?\d{2,4})',
        re.IGNORECASE,
    )
    for m in date_re.finditer(text):
        patterns.append((m.group(1).strip(), 0.8))

    return patterns


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

def build_default_registry() -> TagRegistry:
    """Return a TagRegistry pre-loaded with all built-in detectors."""
    reg = TagRegistry()
    reg.register("modalidad", _detect_modality, "Remote/Hybrid/Onsite detection", priority=10)
    reg.register("horario", _detect_schedule, "Full-time/Part-time/Contract", priority=9)
    reg.register("salario", _detect_salary, "Salary range extraction (EUR/USD)", priority=8)
    reg.register("vacantes", _detect_vacancies, "Number of open positions", priority=7)
    reg.register("postulados", _detect_applicants, "Number of applicants", priority=6)
    reg.register("fecha_publicacion", _detect_publication_date, "Publication date", priority=5)
    return reg

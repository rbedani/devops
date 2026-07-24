"""Tag auto-detection engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Any

from src.models.job import JobTag


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


def _detect_salary(title: str, description: str, _meta: dict[str, Any]) -> list[tuple[str, float]]:
    """Detect salary amounts in EU (€-after-number) and US ($-before-number) formats."""
    text = f"{title} {description}"
    patterns: list[tuple[str, float]] = []
    seen: set[str] = set()

    # --- Regex components ---
    # Currency before number: "$", "USD ", "€", "S/ "
    CURR_BEFORE = r'(?:USD?\s*|\$\s*|€\s*|S/\s*|ARS\s*|CLP\s*|COP\s*)'
    # Currency after number: "€", " USD", " EUR", " $"
    CURR_AFTER = r'(?:\s*€|\s*USD|\s*EUR|\s*\$)?'
    # Number with optional thousands separator and k/K/mil suffix
    NUM = r'\d[\d.,]*\s*(?:k|K|mil)?'
    # Optional range connector
    RANGE = r'(?:\s*[-–aA]\s*)'

    # --- Pattern 1: Keyword + amount (highest confidence) ---
    # "Salario: 45.000€", "Salary: USD 80k-100k", "Compensación: €50.000 a €65.000"
    KW = r'(?:salario|salary|compensaci[oó]n|remuneraci[oó]n|pay|remuneration|sueldo|compensa)'
    keyword_pattern = (
        KW + r'[:\s]*'
        + r'(?:' + CURR_BEFORE + r')?'
        + r'(?:' + CURR_BEFORE + r')?' + NUM + CURR_AFTER
        + r'(?:' + RANGE + r'(?:' + CURR_BEFORE + r')?' + NUM + CURR_AFTER + r')?'
    )
    keyword_re = re.compile(keyword_pattern, re.IGNORECASE)
    for m in keyword_re.finditer(text):
        val = m.group(0).strip()
        if val not in seen:
            patterns.append((val, 0.95))
            seen.add(val)

    # --- Pattern 2: Currency amount without keyword ---
    # "45.000€ a 55.000€", "$120,000", "€80.000"
    currency_pattern = (
        r'(?:' + CURR_BEFORE + r')?'
        + NUM + CURR_AFTER
        + r'(?:' + RANGE + r'(?:' + CURR_BEFORE + r')?' + NUM + CURR_AFTER + r')?'
    )
    currency_re = re.compile(currency_pattern, re.IGNORECASE)
    for m in currency_re.finditer(text):
        val = m.group(0).strip()
        if len(val) < 4 or val in seen:
            continue
        if not any(c.isdigit() for c in val):
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

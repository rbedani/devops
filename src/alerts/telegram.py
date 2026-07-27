"""Telegram alert formatter for job listings.

Formats job data as structured Markdown for Hermes Agent Telegram delivery.
Salary is displayed as EUR gross annual by default (configurable).
"""

from __future__ import annotations

from src.core.models.job import Job

# Default salary context (adjustable per project/region)
SALARY_DEFAULT_CURRENCY = "EUR"
SALARY_DEFAULT_PERIOD = "bruto anual"

# Emoji map for common tags
_TAG_EMOJI: dict[str, str] = {
    "modalidad": "🏠",
    "salario": "💰",
    "horario": "🕐",
    "ubicacion": "📍",
    "vacantes": "👥",
    "postulados": "📋",
    "fecha_publicacion": "📅",
}


def _format_salary(raw: str) -> str:
    """Normalise a raw salary value for display.

    Adds currency symbol and period if missing.
    Converts bare numbers to EUR display.
    """
    raw = raw.strip()

    # Already has currency symbol
    if any(sym in raw for sym in ["€", "$", "USD", "EUR", "£"]):
        return raw

    # Bare number or range (e.g. "45.000-55.000", "50k-65k")
    if raw and any(c.isdigit() for c in raw):
        return f"€{raw} {SALARY_DEFAULT_PERIOD}"

    return raw


def format_job_alert(job: Job) -> str:
    """Format a single job as a Telegram-ready Markdown message."""
    lines: list[str] = []

    # Header
    lines.append(f"💼 *{job.title}*")
    lines.append("")

    # Core info
    if job.company:
        lines.append(f"🏢 {job.company}")
    if job.location:
        lines.append(f"📍 {job.location}")

    lines.append("")

    # Tags
    tag_lines: list[str] = []
    for tag in job.tags:
        emoji = _TAG_EMOJI.get(tag.key, "🏷️")
        value = _format_salary(tag.value) if tag.key == "salario" else tag.value
        tag_lines.append(f"{emoji} *{tag.key.title()}:* {value}")

    if tag_lines:
        lines.append("\n".join(tag_lines))
        lines.append("")

    # Link
    lines.append(f"🔗 [Ver oferta]({job.url})")

    return "\n".join(lines)


def format_jobs_table(jobs: list[Job], title: str = "📋 Ofertas de empleo") -> str:
    """Format multiple jobs as a compact Telegram message."""
    if not jobs:
        return f"{title}\n\n_No se encontraron ofertas._"

    lines: list[str] = [f"*{title}*", f"_Total: {len(jobs)} oferta(s)_", ""]

    for i, job in enumerate(jobs, 1):
        parts = [f"*{i}.* [{job.title}]({job.url})"]
        if job.company:
            parts.append(f"🏢 {job.company}")
        if job.location:
            parts.append(f"📍 {job.location}")

        modality = job.get_tag("modalidad")
        if modality:
            parts.append(f"🏠 {modality}")

        salary = job.get_tag("salario")
        if salary:
            parts.append(f"💰 {_format_salary(salary)}")

        lines.append(" · ".join(parts))

    lines.append("")
    lines.append("_Scrapeado automáticamente por Framework Browser Jobs_")

    return "\n".join(lines)


def format_jobs_markdown_table(jobs: list[Job]) -> str:
    """Format jobs as a structured Markdown block."""
    if not jobs:
        return "_Sin resultados._"

    lines: list[str] = []

    for job in jobs:
        salary = job.get_tag("salario")
        salary_display = _format_salary(salary) if salary else "No especificado"

        row = (
            f"*{job.title}*\n"
            f"  🏢 {job.company or 'N/A'} | 📍 {job.location or 'N/A'}\n"
            f"  🏠 {job.get_tag('modalidad') or 'N/A'} | "
            f"💰 {salary_display}\n"
            f"  🕐 {job.get_tag('horario') or 'N/A'} | "
            f"📅 {job.get_tag('fecha_publicacion') or 'N/A'}\n"
            f"  🔗 [Abrir]({job.url})"
        )
        lines.append(row)
        lines.append("")

    return "\n".join(lines)

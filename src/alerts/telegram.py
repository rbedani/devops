"""Telegram alert formatter for job listings.

Formats job data as a structured Markdown table suitable for
Hermes Agent Telegram delivery.
"""

from __future__ import annotations

from src.models.job import Job


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
        tag_lines.append(f"{emoji} *{tag.key.title()}:* {tag.value}")

    if tag_lines:
        lines.append("\n".join(tag_lines))
        lines.append("")

    # Link
    lines.append(f"🔗 [Ver oferta]({job.url})")

    return "\n".join(lines)


def format_jobs_table(jobs: list[Job], title: str = "📋 Ofertas de empleo") -> str:
    """Format multiple jobs as a structured Telegram message with a table-like layout."""
    if not jobs:
        return f"{title}\n\n_No se encontraron ofertas._"

    lines: list[str] = [f"*{title}*", f"_Total: {len(jobs)} oferta(s)_", ""]

    for i, job in enumerate(jobs, 1):
        # Compact one-liner per job
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
            parts.append(f"💰 {salary}")

        lines.append(" · ".join(parts))

    lines.append("")
    lines.append("_Scrapeado automáticamente por Framework Browser Jobs_")

    return "\n".join(lines)


def format_jobs_markdown_table(jobs: list[Job]) -> str:
    """Format jobs as a real Markdown table (pipe syntax).

    Note: Telegram renders this as a readable text block since
    it doesn't support full Markdown tables, but the structure
    is clear and scannable.
    """
    if not jobs:
        return "_Sin resultados._"

    lines: list[str] = []

    for job in jobs:
        row = (
            f"*{job.title}*\n"
            f"  🏢 {job.company or 'N/A'} | 📍 {job.location or 'N/A'}\n"
            f"  🏠 {job.get_tag('modalidad') or 'N/A'} | "
            f"💰 {job.get_tag('salario') or 'N/A'} | "
            f"🕐 {job.get_tag('horario') or 'N/A'}\n"
            f"  📅 {job.get_tag('fecha_publicacion') or 'N/A'} | "
            f"👥 {job.get_tag('postulados') or 'N/A'}\n"
            f"  🔗 [Abrir]({job.url})"
        )
        lines.append(row)
        lines.append("")  # separator

    return "\n".join(lines)

"""FastAPI routes for the STATUS module — dashboard listing, table, filters, status management.

Extracted from src/dashboard/server.py as part of the 5-layer architecture.
Templates remain shared at src/dashboard/templates/.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from src.core.config.settings import DB_PATH as _CORE_DB_PATH
from src.core.db.database import update_job_status as _update_job_status
from src.scan.runner import scan_state
from src.status.filters import DEFAULT_FILTERS

# -- Paths -------------------------------------------------------------------

HERE = Path(__file__).parent
TEMPLATE_DIR = HERE.parent / "dashboard" / "templates"

# -- Config ------------------------------------------------------------------

DB_PATH: str = str(_CORE_DB_PATH)
DEBUG_MODE: bool = os.environ.get("DEBUG_MODE") is not None

# -- Sort whitelist ----------------------------------------------------------

SORT_WHITELIST: dict[str, str] = {
    "date_published": (
        "(SELECT json_extract(value, '$.value') FROM json_each(tags) "
        "WHERE json_extract(value, '$.key') = 'fecha_publicacion')"
    ),
    "platform": "source",
    "title": "title",
    "company": "company",
    "modality": (
        "(SELECT json_extract(value, '$.value') FROM json_each(tags) "
        "WHERE json_extract(value, '$.key') = 'modalidad')"
    ),
    "salary": (
        "CAST((SELECT json_extract(value, '$.value') FROM json_each(tags) "
        "WHERE json_extract(value, '$.key') = 'salario') AS INTEGER)"
    ),
    "location": "location",
    "status": "status",
}

# -- Templates ---------------------------------------------------------------

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# -- Router ------------------------------------------------------------------

status_router = APIRouter(tags=["status"])


# -- Helpers -----------------------------------------------------------------


def get_connection() -> sqlite3.Connection:
    """Open a direct sqlite3 connection to the jobs DB."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _extract_tags(tags_json: str) -> dict[str, str]:
    """Parse tags JSON column into a key→value dict."""
    try:
        tags = json.loads(tags_json)
        return {t["key"]: t["value"] for t in tags}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def _format_datetime(dt_str: str, fallback_time: str = "") -> str:
    """Format ISO datetime to dd/mm/YY HH:MM (Europe/Madrid timezone)."""
    if not dt_str:
        return ""
    from datetime import datetime
    try:
        dt_str_clean = dt_str.replace("T", " ").replace("Z", "").split(".")[0]
        dt = datetime.strptime(dt_str_clean, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%y %H:%M")
    except (ValueError, IndexError):
        pass
    try:
        dt = datetime.strptime(dt_str.strip(), "%Y-%m-%d")
        if fallback_time and len(fallback_time) >= 5:
            time_part = fallback_time[11:16]
            combined = f"{dt_str.strip()} {time_part}"
            dt_full = datetime.strptime(combined, "%Y-%m-%d %H:%M")
            return dt_full.strftime("%d/%m/%y %H:%M")
        return dt.strftime("%d/%m/%y")
    except (ValueError, IndexError):
        return dt_str


def _parse_sort(sort_param: str | None) -> str:
    """Parse 'col:dir,col:dir' → SQL ORDER BY clause.

    Validates each column against SORT_WHITELIST. Invalid or missing
    columns are silently skipped. Falls back to 'scraped_at DESC'.
    """
    if not sort_param:
        return "scraped_at DESC"

    parts = sort_param.split(",")
    clauses: list[str] = []
    for part in parts:
        part = part.strip()
        if ":" not in part:
            continue
        col, _, direction = part.partition(":")
        direction = direction.strip().lower()
        if direction not in ("asc", "desc"):
            continue
        col = col.strip()
        if col in SORT_WHITELIST:
            clauses.append(f"{SORT_WHITELIST[col]} {direction.upper()}")

    return ", ".join(clauses) if clauses else "scraped_at DESC"


def _fetch_jobs(
    conn: sqlite3.Connection,
    search: str = "",
    per_page: int = 10,
    offset: int = 0,
    since: str = "",
    active_filters: list[str] | None = None,
    order_by: str = "scraped_at DESC",
) -> tuple[list[dict], int]:
    """Query jobs with optional search, pagination, date filter, and active filters."""
    if active_filters is None:
        active_filters = []

    date_clause = ""
    if since == "24h":
        date_clause = (
            "COALESCE("
            "(SELECT json_extract(value, '$.value') FROM json_each(tags) "
            "WHERE json_extract(value, '$.key') = 'fecha_publicacion'), "
            "substr(scraped_at, 1, 10)"
            ") >= strftime('%Y-%m-%d', 'now', '-24 hours')"
        )
    elif since == "7d":
        date_clause = (
            "COALESCE("
            "(SELECT json_extract(value, '$.value') FROM json_each(tags) "
            "WHERE json_extract(value, '$.key') = 'fecha_publicacion'), "
            "substr(scraped_at, 1, 10)"
            ") >= strftime('%Y-%m-%d', 'now', '-7 days')"
        )
    elif since == "30d":
        date_clause = (
            "COALESCE("
            "(SELECT json_extract(value, '$.value') FROM json_each(tags) "
            "WHERE json_extract(value, '$.key') = 'fecha_publicacion'), "
            "substr(scraped_at, 1, 10)"
            ") >= strftime('%Y-%m-%d', 'now', '-30 days')"
        )

    filter_clauses = DEFAULT_FILTERS.build_where_clauses(active_filters)

    if search:
        # Split on whitespace AND commas, so "2514 2475 2473" and
        # "2514, 2475, 2473" delimit tokens identically.
        tokens = [t for t in re.split(r"[\s,]+", search.strip()) if t]
        word_tokens = [t for t in tokens if not t.isdigit()]
        id_tokens = [t for t in tokens if t.isdigit()]

        text_columns = ["title", "company", "location", "description", "tags"]
        clauses: list[str] = []
        params: list[str] = []

        # Non-numeric words: each must match ANY text column (AND between
        # words, so "madrid remoto" means the row contains both, anywhere).
        for word in word_tokens:
            col_clause = " OR ".join(f"{col} LIKE ?" for col in text_columns)
            clauses.append(f"({col_clause})")
            params.extend([f"%{word}%"] * len(text_columns))

        # Numeric tokens are job IDs: ANY of them may match (OR), by exact
        # ID or by containing the digits in a text column.
        if id_tokens:
            id_alternatives: list[str] = []
            for id_str in id_tokens:
                id_cols = [f"CAST(id AS TEXT) = ?"] + [
                    f"{col} LIKE ?" for col in text_columns
                ]
                id_alternatives.append("(" + " OR ".join(id_cols) + ")")
                params.append(id_str)
                params.extend([f"%{id_str}%"] * len(text_columns))
            clauses.append("(" + " OR ".join(id_alternatives) + ")")

        where_parts = []
        if date_clause:
            where_parts.append(date_clause)
        if clauses:
            where_parts.append(" AND ".join(clauses))
        where_parts.extend(filter_clauses)
        where = "WHERE " + " AND ".join(f"({p})" for p in where_parts) if where_parts else ""

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM jobs {where}", params
        ).fetchone()
        total = count_row[0]

        if per_page > 0:
            rows = conn.execute(
                f"SELECT * FROM jobs {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
                (*params, per_page, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM jobs {where} ORDER BY {order_by}",
                params,
            ).fetchall()
    else:
        where_parts = []
        if date_clause:
            where_parts.append(date_clause)
        where_parts.extend(filter_clauses)
        where_suffix = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        count_query = f"SELECT COUNT(*) FROM jobs{where_suffix}"
        query = f"SELECT * FROM jobs{where_suffix} ORDER BY {order_by}"

        total = conn.execute(count_query).fetchone()[0]

        if per_page > 0:
            rows = conn.execute(
                f"{query} LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()
        else:
            rows = conn.execute(query).fetchall()

    jobs = []
    for row in rows:
        keys = row.keys() if hasattr(row, "keys") else []
        tag_dict = _extract_tags(row["tags"] if "tags" in keys else "[]")
        jobs.append({
            "id": row["id"],
            "date_published": _format_datetime(tag_dict.get("fecha_publicacion", ""), row["scraped_at"] if "scraped_at" in keys else ""),  # noqa: E501
            "platform": row["source"],
            "title": row["title"],
            "company": row["company"] or "",
            "modality": tag_dict.get("modalidad", ""),
            "salary": tag_dict.get("salario", ""),
            "location": row["location"] or "",
            "link": row["url"],
            "status": row["status"] if "status" in keys else "",
        })

    return jobs, total


# -- Routes ------------------------------------------------------------------


@status_router.get("/status/panel", response_class=HTMLResponse)
async def status_panel(request: Request) -> HTMLResponse:
    """Render the STATUS tab content — table with filters, pagination.

    Reuses the existing index page logic: renders the full STATUS view
    (search, filters, SELECT, AUTO-APPLY, table skeleton) as an HTMX
    partial that swaps into #main-content.
    """
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    return templates.TemplateResponse(
        request, "partials/status_panel.html",
        {
            "total_jobs": total,
            "debug_mode": DEBUG_MODE,
            "scan_running": scan_state.running,
            "filters": DEFAULT_FILTERS.filters,
            "active_filters": [],
        },
    )


@status_router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Full dashboard page — renders the main shell with job table."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    return templates.TemplateResponse(
        request, "index.html",
        {
            "total_jobs": total,
            "debug_mode": DEBUG_MODE,
            "scan_running": scan_state.running,
            "filters": DEFAULT_FILTERS.filters,
            "active_filters": [],
        },
    )


@status_router.get("/table", response_class=HTMLResponse)
async def table(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=0),
    search: str = Query(""),
    select: bool = Query(False),
    since: str = Query(""),
    filters: str = Query(""),
    sort: str = Query(""),
) -> HTMLResponse:
    """Job table partial — HTMX-swappable, with pagination, search, date filter,
    modular filter system, and dynamic sort."""
    active_filters = [f.strip() for f in filters.split(",") if f.strip()]
    order_by = _parse_sort(sort if sort else None)
    conn = get_connection()
    offset = (page - 1) * per_page if per_page > 0 else 0
    jobs, total = _fetch_jobs(conn, search=search, per_page=per_page, offset=offset, since=since, active_filters=active_filters, order_by=order_by)  # noqa: E501
    conn.close()

    total_pages = max(1, (total + per_page - 1) // per_page) if per_page > 0 else 1
    show_all = per_page == 0

    return templates.TemplateResponse(
        request, "partials/table.html",
        {
            "jobs": jobs,
            "page": page,
            "per_page": per_page if per_page > 0 else total,
            "total": total,
            "total_pages": total_pages,
            "search": search,
            "select": select,
            "show_all": show_all,
            "since": since,
            "active_filters": active_filters,
            "sort": sort,
        },
    )


@status_router.post("/clean-db")
async def clean_database(request: Request) -> HTMLResponse:
    """Delete all job records from the database.

    Also stops any running scan so the SCAN button re-enables.
    """
    scan_state.cancel.set()

    conn = get_connection()
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()
    return templates.TemplateResponse(
        request, "settings.html",
        {"request": request, "cleaned": "status"},
    )

@status_router.post("/job/{job_id}/status")
async def manual_status(job_id: int, request: Request) -> JSONResponse:
    """Manually set a job's status from JSON body.

    Body: {"status": "postulado"}
    Returns {"ok": true} on success, 404 if job not found.
    """
    body = await request.json()
    status = body.get("status", "")

    updated = _update_job_status(job_id, status, DB_PATH)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")

    return JSONResponse({"ok": True})


# ===========================================================================
# SETTINGS ROUTE
# ===========================================================================


@status_router.get("/settings", response_class=HTMLResponse)
async def settings_panel(request: Request) -> HTMLResponse:
    """Render the SETTINGS tab — dashboard configuration panel."""
    return templates.TemplateResponse(
        request, "settings.html",
        {
            "request": request,
        },
    )
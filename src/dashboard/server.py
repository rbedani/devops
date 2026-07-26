"""FastAPI dashboard server — routes, migration, SSE scan progress.

Serves the job listing dashboard with HTMX-driven partials, pagination,
search, status column management, and real-time scan progress via SSE.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import AsyncGenerator
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.dashboard.scan import run_scan, scan_state
from src.dashboard.filters import DEFAULT_FILTERS
from src.datos.routes import datos_router
from src.datos.store import get_cv, get_fields, get_connection as get_datos_connection, run_datos_migration
from src.apply.auto_apply import AutoApply

# -- Paths -------------------------------------------------------------------

HERE = Path(__file__).parent
TEMPLATE_DIR = HERE / "templates"
STATIC_DIR = HERE / "static"
DB_PATH = "jobs.db"
DEBUG_MODE: bool = os.environ.get("DEBUG_MODE") is not None

# -- Templates ---------------------------------------------------------------

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


# -- Migration ---------------------------------------------------------------

def run_migration(db_path: str) -> None:
    """Create jobs table and add status column if not present (idempotent).

    Spec: Requirement 9 — Status Migration.
    Creates the table if missing (handles fresh DB after deletion).
    Then additively adds the status column. Never drops or alters
    existing columns. Wrapped in try/except for idempotency.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT    NOT NULL,
                title       TEXT    NOT NULL,
                url         TEXT    NOT NULL UNIQUE,
                company     TEXT,
                location    TEXT,
                description TEXT,
                tags        TEXT    DEFAULT '[]',
                scraped_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
            CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
        """)
        conn.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists — idempotent
        conn.rollback()
    finally:
        conn.close()


# -- Lifespan ----------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run migration on startup, clean up on shutdown."""
    run_migration(DB_PATH)
    run_datos_migration(DB_PATH)
    yield


# -- App ---------------------------------------------------------------------

app = FastAPI(title="Job Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(datos_router)


# -- Helpers -----------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """Open a direct sqlite3 connection to the jobs DB.

    Dashboard uses its own connection (not JobDatabase) to avoid modifying
    existing src/db/ code. Uses the same DB file and row_factory pattern.
    """
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
    """Format ISO datetime to dd/mm/YY HH:MM (Europe/Madrid timezone).

    If dt_str has only date (no time), uses fallback_time (scraped_at)
    to complete the time portion. This gives a meaningful datetime
    close to the actual publication moment.
    """
    if not dt_str:
        return ""
    from datetime import datetime
    try:
        dt_str_clean = dt_str.replace("T", " ").replace("Z", "").split(".")[0]
        dt = datetime.strptime(dt_str_clean, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%y %H:%M")
    except (ValueError, IndexError):
        pass
    # Date only — use fallback_time to add the time
    try:
        dt = datetime.strptime(dt_str.strip(), "%Y-%m-%d")
        if fallback_time and len(fallback_time) >= 5:
            time_part = fallback_time[11:16]  # HH:MM from "2026-07-25 14:30:00"
            combined = f"{dt_str.strip()} {time_part}"
            dt_full = datetime.strptime(combined, "%Y-%m-%d %H:%M")
            return dt_full.strftime("%d/%m/%y %H:%M")
        return dt.strftime("%d/%m/%y")
    except (ValueError, IndexError):
        return dt_str


def _fetch_jobs(
    conn: sqlite3.Connection,
    search: str = "",
    per_page: int = 10,
    offset: int = 0,
    since: str = "",
    active_filters: list[str] | None = None,
) -> tuple[list[dict], int]:
    """Query jobs with optional search, pagination, date filter, and active filters.

    `since` values: 24h, 7d, 30d — filters by scraped_at.
    Empty string means no time restriction.

    `active_filters`: list of filter keys from the FilterRegistry; each
    active filter adds its WHERE clause to the query.
    """
    if active_filters is None:
        active_filters = []

    date_clause = ""
    date_params: list[str] = []
    if since == "24h":
        date_clause = "scraped_at >= datetime('now', '-24 hours')"
    elif since == "7d":
        date_clause = "scraped_at >= datetime('now', '-7 days')"
    elif since == "30d":
        date_clause = "scraped_at >= datetime('now', '-30 days')"

    filter_clauses = DEFAULT_FILTERS.build_where_clauses(active_filters)

    if search:
        words = search.split()
        columns = ["title", "company", "location", "description", "tags"]
        word_clauses = []
        params: list[str] = []
        for word in words:
            col_clause = " OR ".join(f"{col} LIKE ?" for col in columns)
            word_clauses.append(f"({col_clause})")
            params.extend([f"%{word}%"] * len(columns))

        where_parts = []
        if date_clause:
            where_parts.append(date_clause)
        if word_clauses:
            where_parts.append(" OR ".join(word_clauses))
        where_parts.extend(filter_clauses)
        where = "WHERE " + " AND ".join(f"({p})" for p in where_parts) if where_parts else ""

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM jobs {where}", params
        ).fetchone()
        total = count_row[0]

        if per_page > 0:
            rows = conn.execute(
                f"SELECT * FROM jobs {where} ORDER BY scraped_at DESC LIMIT ? OFFSET ?",
                (*params, per_page, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM jobs {where} ORDER BY scraped_at DESC",
                params,
            ).fetchall()
    else:
        where_parts = []
        if date_clause:
            where_parts.append(date_clause)
        where_parts.extend(filter_clauses)
        where_suffix = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        count_query = f"SELECT COUNT(*) FROM jobs{where_suffix}"
        query = f"SELECT * FROM jobs{where_suffix} ORDER BY scraped_at DESC"

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
            "date_published": _format_datetime(tag_dict.get("fecha_publicacion", ""), row["scraped_at"] if "scraped_at" in keys else ""),
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

@app.get("/", response_class=HTMLResponse)
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


@app.get("/table", response_class=HTMLResponse)
async def table(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=0),
    search: str = Query(""),
    select: bool = Query(False),
    since: str = Query(""),
    filters: str = Query(""),
) -> HTMLResponse:
    """Job table partial — HTMX-swappable, with pagination, search, date filter,
    and modular filter system.

    Columns: date_published, platform, title, company, modality, salary,
    location, link, status.

    The `since` param filters by scraped_at: 24h, 7d, 30d.
    `filters` is a comma-separated list of active filter keys
    (e.g. 'hide_postulado,hide_errores').
    """
    active_filters = [f.strip() for f in filters.split(",") if f.strip()]
    conn = get_connection()
    offset = (page - 1) * per_page if per_page > 0 else 0
    jobs, total = _fetch_jobs(conn, search=search, per_page=per_page, offset=offset, since=since, active_filters=active_filters)
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
        },
    )


@app.post("/clean-db")
async def clean_database(request: Request) -> HTMLResponse:
    """Delete all job records from the database.

    Also stops any running scan so the SCAN button re-enables.
    """
    # Stop any running scan first — cancel event will be cleared by run_scan()
    scan_state.cancel.set()
    if scan_state.running:
        await asyncio.sleep(0.2)
    if scan_state.running:
        scan_state.reset()

    conn = get_connection()
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()
    return HTMLResponse("")

@app.get("/scan", response_class=HTMLResponse)
async def trigger_scan(
    request: Request,
    q: str = Query(""),
    debug_mode: str = Query(""),
    platforms: list[str] = Query([]),
) -> HTMLResponse:
    """Trigger an async scan and return progress partial.
    
    If a scan is already running, returns the current progress without
    starting a new one. debug_mode=on limits results to 3 per scraper.
    The q param is passed as a keyword to the subprocess for post-scrape
    title/company filtering.
    The platforms param specifies which platforms to scan (e.g. linkedin).
    """
    if not scan_state.running:
        # Reset state
        scan_state.running = True
        scan_state.progress_pct = 0.0
        scan_state.current_target = ""
        scan_state.targets_completed = 0
        scan_state.targets_total = 0
        scan_state.log_lines = []
        scan_state.error = None

        is_debug = debug_mode == "on"

        # Fire-and-forget background task
        asyncio.create_task(run_scan(scan_state, debug=is_debug, keyword=q, platforms=platforms))

    return templates.TemplateResponse(
        request, "partials/progress.html",
        {"state": scan_state, "debug_mode": debug_mode == "on"},
    )


@app.get("/scan/stop", response_class=HTMLResponse)
async def stop_scan(request: Request) -> HTMLResponse:
    """Stop a running scan — sets cancellation event and returns progress partial.

    The cancel event signals run_scan() to terminate the subprocess and break
    the platform loop. The returned progress partial refreshes the UI via HTMX
    so the STOP button disappears.

    If the scan task already died (e.g. external crash), also forcibly resets
    state to unstick a stale `running=True`.
    """
    scan_state.cancel.set()
    if scan_state.running:
        await asyncio.sleep(0.2)
    if scan_state.running:
        scan_state.reset()  # cancel event is fresh and unset — next run_scan() will clear() it
    return templates.TemplateResponse(
        request, "partials/progress.html",
        {"state": scan_state, "debug_mode": DEBUG_MODE},
    )


@app.get("/scan/status")
async def scan_status(request: Request) -> StreamingResponse:
    """SSE endpoint streaming scan progress events.

    Emits JSON events with pct, target, completed, total, log, and done
    fields. The client (EventSource in script.js) receives these and
    updates the progress bar.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        while scan_state.running:
            data = {
                "pct": scan_state.progress_pct,
                "target": scan_state.current_target,
                "completed": scan_state.targets_completed,
                "total": scan_state.targets_total,
                "log": scan_state.log_lines[-1] if scan_state.log_lines else "",
                "done": False,
            }
            yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(0.5)

        # Final event
        data = {
            "pct": 100.0,
            "done": True,
            "error": scan_state.error,
        }
        yield f"data: {json.dumps(data)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/select/toggle", response_class=HTMLResponse)
async def toggle_select(
    request: Request,
    enabled: bool = Query(False),
) -> HTMLResponse:
    """Toggle checkbox column visibility.

    Returns the table partial with select enabled/disabled so HTMX can
    swap the column in/out.
    """
    # Re-fetch table data with select state
    conn = get_connection()
    per_page = 10
    jobs, total = _fetch_jobs(conn, search="", per_page=per_page, offset=0)
    conn.close()

    total_pages = max(1, (total + per_page - 1) // per_page) if per_page > 0 else 1

    return templates.TemplateResponse(
        request, "partials/table.html",
        {
            "jobs": jobs,
            "page": 1,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "search": "",
            "select": enabled,
            "show_all": False,
            "active_filters": [],
        },
    )


# -- Status helpers ---------------------------------------------------------


def _update_job_status(job_id: int, status: str) -> bool:
    """Set the status column for a job row. Returns True if row existed."""
    conn = get_connection()
    cursor = conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# -- Status routes ----------------------------------------------------------


@app.post("/job/{job_id}/status")
async def manual_status(job_id: int, request: Request) -> JSONResponse:
    """Manually set a job's status from JSON body.

    Body: {"status": "postulado"}
    Returns {"ok": true} on success, 404 if job not found.
    """
    body = await request.json()
    status = body.get("status", "")

    updated = _update_job_status(job_id, status)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")

    return JSONResponse({"ok": True})


@app.post("/apply/auto")
async def auto_apply(request: Request) -> JSONResponse:
    """Run auto-apply for selected job IDs sequentially.

    Body: {"job_ids": [1, 2, 3]}
    Returns {"results": [{"id": 1, "status": "postulado"}, ...]}
    """
    body = await request.json()
    job_ids = body.get("job_ids", [])

    # Load profile fields and CV from datos store
    datos_conn = get_datos_connection(DB_PATH)
    fields = get_fields(datos_conn)
    cv = get_cv(datos_conn)
    datos_conn.close()

    profile_fields = [{"name": f.name, "field_type": f.field_type, "value": f.value} for f in fields]
    cv_path = cv.file_path if cv else None

    applier = AutoApply(profile_fields=profile_fields, cv_path=cv_path)

    results: list[dict] = []
    for job_id in job_ids:
        # Get job URL from DB
        conn = get_connection()
        row = conn.execute("SELECT url FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()

        if row is None:
            results.append({"id": job_id, "status": "general-error", "error": "Job not found"})
            continue

        url = row["url"]
        status = await applier.apply(url)
        _update_job_status(job_id, status)
        results.append({"id": job_id, "status": status})

    return JSONResponse({"results": results})



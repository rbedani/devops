"""FastAPI routes for the SCAN module — scan execution and platform management.

Migrated from src/dashboard/server.py (scan routes) and src/datos/routes.py
(platform routes) as part of the 5-layer architecture extraction.

All routes return HTMX-compatible HTML partials.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from src.core.config.settings import DB_PATH as _CORE_DB_PATH
from src.scan.runner import run_scan, scan_state
from src.scan.store import (
    get_connection,
    get_enabled_platform_names,
    get_platforms,
    toggle_platform,
)

# -- Paths -------------------------------------------------------------------

TEMPLATE_DIR = Path(__file__).parent.parent / "dashboard" / "templates"
SCAN_PARAMS_PATH = Path(__file__).parent.parent.parent / "config" / "scan_params.json"

# -- Templates ---------------------------------------------------------------

from fastapi.templating import Jinja2Templates  # noqa: E402

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# -- Router ------------------------------------------------------------------

scan_router = APIRouter(tags=["scan"])

# Make DB_PATH patchable (same as server.py pattern)
DB_PATH: str = str(_CORE_DB_PATH)
DEBUG_MODE: bool = os.environ.get("DEBUG_MODE") is not None


# -- Helpers -----------------------------------------------------------------

def _get_conn():
    return get_connection(DB_PATH)


def _load_saved_params() -> dict:
    """Load scan params from saved JSON file."""
    if SCAN_PARAMS_PATH.exists():
        try:
            return json.loads(SCAN_PARAMS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_params(data: dict) -> None:
    """Save scan params to JSON file. Delete file if keywords is empty (restore defaults)."""
    if not data.get("keywords", "").strip():
        SCAN_PARAMS_PATH.unlink(missing_ok=True)
        return
    SCAN_PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCAN_PARAMS_PATH.write_text(json.dumps(data, indent=2))


# ===========================================================================
# SCAN EXECUTION ROUTES
# ===========================================================================


@scan_router.get("/scan/config", response_class=HTMLResponse)
async def scan_config(request: Request) -> HTMLResponse:
    """Render the SCAN tab content — platforms, search targets, run button, progress, log viewer."""
    conn = _get_conn()
    from src.scan.store import get_platforms
    platforms = get_platforms(conn)
    conn.close()

    # Load saved params first, fall back to targets.json defaults
    saved = _load_saved_params()
    keyword = saved.get("keywords", "")
    location = saved.get("location", "")
    modalities: list[str] = saved.get("modalities", [])
    date_range = saved.get("date_range", "")

    if not keyword:
        # Fallback: read from targets.json
        try:
            from src.core.config.search import load_targets
            from src.core.config.settings import TARGETS_PATH
            targets = load_targets(TARGETS_PATH)
            if targets:
                kw = targets[0].filters.keywords
                keyword = ", ".join(kw) if kw else ""
                if not location:
                    location = ", ".join(targets[0].filters.countries) if targets[0].filters.countries else ""  # noqa: E501
                if not modalities:
                    modalities = [m.lower() for m in targets[0].filters.modalities]
                if not date_range:
                    date_range = targets[0].filters.date_range
        except Exception:
            pass

    return templates.TemplateResponse(
        request, "scan_config.html",
        {
            "request": request,
            "platforms": platforms,
            "scan_state": scan_state,
            "keyword": keyword,
            "location": location,
            "modalities": modalities,
            "date_range": date_range,
        },
    )


@scan_router.post("/scan/config/save", response_class=HTMLResponse)
async def scan_config_save(
    request: Request,
    q: str = Form(""),
    location: str = Form(""),
    modality: list[str] = Form([]),  # noqa: B008
    date_range: str = Form(""),
) -> HTMLResponse:
    """Save scan parameters to persistent storage."""
    _save_params({
        "keywords": q,
        "location": location,
        "modalities": modality,
        "date_range": date_range,
    })
    return HTMLResponse("""<div class="save-toast">✓ Saved</div>""")


@scan_router.get("/scan", response_class=HTMLResponse)
async def trigger_scan(
    request: Request,
    q: str = Query(""),
    location: str = Query(""),
    modality: list[str] = Query([]),  # noqa: B008
    date_range: str = Query(""),
    debug_mode: str = Query(""),
) -> HTMLResponse:
    """Trigger an async scan and return progress partial.

    If a scan is already running, returns the current progress without
    starting a new one. debug_mode=on limits results to 3 per scraper.
    The q param is passed as SCAN_KEYWORD to the subprocess for post-scrape
    title/company filtering.
    The location, modality, and date_range params are passed as env vars
    to the subprocess for search configuration.
    Enabled platforms are read from the database (single source of truth).
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

        # Read enabled platforms from DB (single source of truth)
        conn = _get_conn()
        enabled_platforms = get_enabled_platform_names(conn)
        conn.close()

        # Fire-and-forget background task
        import asyncio
        scan_state._scan_task = asyncio.create_task(run_scan(
            scan_state,
            debug=is_debug,
            keyword=q,
            platforms=enabled_platforms,
            location=location,
            modality=modality,
            date_range=date_range,
        ))

    return templates.TemplateResponse(
        request, "partials/progress.html",
        {"state": scan_state, "debug_mode": debug_mode == "on"},
    )


@scan_router.get("/scan/stop", response_class=HTMLResponse)
async def stop_scan(request: Request) -> HTMLResponse:
    """Stop a running scan — sets cancellation event and returns progress partial.

    The cancel event signals run_scan() to terminate the subprocess and break
    the platform loop. The returned progress partial refreshes the UI via HTMX
    so the STOP button disappears. run_scan()'s finally block handles cleanup.
    """
    scan_state.cancel.set()
    if scan_state._scan_task is not None and not scan_state._scan_task.done():
        scan_state._scan_task.cancel()
    return templates.TemplateResponse(
        request, "partials/progress.html",
        {"state": scan_state, "debug_mode": DEBUG_MODE},
    )


@scan_router.get("/scan/status-check", response_class=HTMLResponse)
async def scan_status_check(request: Request) -> HTMLResponse:
    """Return current scan progress as HTML partial (no SSE, one-shot)."""
    return templates.TemplateResponse(
        request, "partials/progress.html",
        {"state": scan_state, "debug_mode": DEBUG_MODE},
    )


@scan_router.get("/scan/status")
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

    import asyncio
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ===========================================================================
# PLATFORM ROUTES
# ===========================================================================


@scan_router.get("/datos/platforms", response_class=HTMLResponse)
async def datos_platforms(request: Request) -> HTMLResponse:
    """Platform list partial."""
    conn = _get_conn()
    platforms = get_platforms(conn)
    conn.close()
    return templates.TemplateResponse(
        request, "partials/scan/platforms.html",
        {"platforms": platforms},
    )


@scan_router.post("/datos/platforms/toggle/{platform_id}", response_class=HTMLResponse)
async def datos_platforms_toggle(
    request: Request, platform_id: int,
) -> HTMLResponse:
    """Toggle enabled/disabled for a platform."""
    conn = _get_conn()
    try:
        new_state = toggle_platform(conn, platform_id)
        if new_state is None:
            return HTMLResponse("Platform not found", status_code=404)
        platforms = get_platforms(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/scan/platforms.html",
        {"platforms": platforms},
    )
"""FastAPI router for job-dashboard API endpoints.

Routes:
  POST /api/apply/auto — trigger auto-apply for selected job IDs
  GET  /api/status    — healthcheck for Hermes Agent
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from src.core.config.settings import DB_PATH as _CORE_DB_PATH
from src.core.db.database import update_job_status as _update_job_status
from src.datos.store import get_cv, get_fields, get_connection as get_datos_connection
from src.apply.auto_apply import AutoApply

router = APIRouter(prefix="/api", tags=["api"])

# Module-level DB_PATH (patchable by tests)
DB_PATH: str = str(_CORE_DB_PATH)


# -- Routes --------------------------------------------------------------------


@router.post("/apply/auto")
async def api_auto_apply(request: Request) -> JSONResponse:
    """Run auto-apply for selected job IDs sequentially.

    Body: {"job_ids": [1, 2, 3]}
    Returns {"results": [{"id": 1, "status": "postulado"}, ...]}
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    job_ids = body.get("job_ids", [])
    if not isinstance(job_ids, list):
        raise HTTPException(status_code=400, detail="job_ids must be a list")

    # Load profile fields and CV from datos store
    datos_conn = get_datos_connection(DB_PATH)
    fields = get_fields(datos_conn)
    cv = get_cv(datos_conn)
    datos_conn.close()

    profile_fields = [
        {"name": f.name, "field_type": f.field_type, "value": f.value}
        for f in fields
    ]
    cv_path = cv.file_path if cv else None

    applier = AutoApply(profile_fields=profile_fields, cv_path=cv_path)

    results: list[dict] = []
    for job_id in job_ids:
        # Get job URL from DB
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT url FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        conn.close()

        if row is None:
            results.append(
                {
                    "id": job_id,
                    "status": "general-error",
                    "error": "Job not found",
                }
            )
            continue

        url = row["url"]
        status = await applier.apply(url)
        _update_job_status(job_id, status, DB_PATH)
        results.append({"id": job_id, "status": status})

    return JSONResponse({"results": results})


@router.get("/status")
async def api_status() -> dict:
    """Healthcheck endpoint for Hermes Agent."""
    return {
        "service": "job-dashboard",
        "version": "1.0",
        "api": True,
        "mcp": "scaffold",
    }
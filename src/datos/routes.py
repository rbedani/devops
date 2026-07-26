"""FastAPI routes for the datos module — profile fields, CV, scan platforms.

All routes return HTMX-compatible HTML partials.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from src.datos.store import (
    add_field,
    add_platform,
    delete_cv,
    get_connection,
    get_cv,
    get_fields,
    get_platforms,
    remove_field,
    remove_platform,
    save_cv,
    save_fields,
)

# -- Paths -------------------------------------------------------------------

HERE = Path(__file__).parent.parent
TEMPLATE_DIR = HERE / "dashboard" / "templates"
CV_DIR = Path("data") / "cv"

# -- Templates ---------------------------------------------------------------

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# -- Router ------------------------------------------------------------------

datos_router = APIRouter(tags=["datos"])

# Make DB_PATH patchable (same as server.py pattern)
DB_PATH = "jobs.db"

# -- Helpers -----------------------------------------------------------------


def _get_conn():
    return get_connection(DB_PATH)


VALID_FIELD_TYPES = frozenset({
    "numeric", "alphanumeric", "date", "datetime", "text",
    "email", "phone", "url", "file",
})

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$"
)


def _validate_field_value(field_type: str, value: str) -> str | None:
    """Return an error message if the value is invalid for the given type, or None."""
    if not value:
        return None  # empty is OK (optional field)

    if field_type == "numeric":
        try:
            float(value)
        except ValueError:
            return f"Value must be a number for numeric field"
    elif field_type == "email":
        if "@" not in value:
            return "Value must contain @ for email field"
    elif field_type == "url":
        if not (value.startswith("http://") or value.startswith("https://")):
            return "Value must start with http:// or https:// for url field"
        if not _URL_RE.match(value):
            return "Invalid URL format for url field"
    elif field_type == "date":
        if not _DATE_RE.match(value):
            return "Value must be YYYY-MM-DD format for date field"
    elif field_type == "datetime":
        if not _DATETIME_RE.match(value):
            return "Value must be ISO format for datetime field"
    elif field_type not in VALID_FIELD_TYPES:
        return f"Unknown field type: {field_type}"
    # text, alphanumeric, phone, file → any value OK
    return None


# -- Panel (full DATA panel) -------------------------------------------------


@datos_router.get("/datos/panel", response_class=HTMLResponse)
async def datos_panel(request: Request) -> HTMLResponse:
    """Full DATA panel — field list, CV section, platforms."""
    conn = _get_conn()
    fields = get_fields(conn)
    cv = get_cv(conn)
    platforms = get_platforms(conn)
    conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/panel.html",
        {"fields": fields, "cv": cv, "platforms": platforms},
    )


# -- Fields ------------------------------------------------------------------


@datos_router.get("/datos/fields", response_class=HTMLResponse)
async def datos_fields(request: Request) -> HTMLResponse:
    """Field rows partial."""
    conn = _get_conn()
    fields = get_fields(conn)
    conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/field_rows.html",
        {"fields": fields},
    )


@datos_router.post("/datos/fields/save", response_class=HTMLResponse)
async def datos_fields_save(request: Request) -> HTMLResponse:
    """Save all fields — validates values against types, then persists."""
    data = await request.json()
    fields_data = data.get("fields", [])

    # Validate each field's value against its type
    for f in fields_data:
        error = _validate_field_value(f.get("field_type", ""), f.get("value", ""))
        if error:
            return HTMLResponse(error, status_code=400)

    conn = _get_conn()
    try:
        save_fields(conn, fields_data)
        fields = get_fields(conn)
        cv = get_cv(conn)
        platforms = get_platforms(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/panel.html",
        {"fields": fields, "cv": cv, "platforms": platforms},
    )


@datos_router.post("/datos/fields/add", response_class=HTMLResponse)
async def datos_fields_add(
    request: Request,
    field_type: str = Form("text"),
) -> HTMLResponse:
    """Add a new empty field row and return its HTML."""
    # Enforce single file-type field constraint
    if field_type == "file":
        conn = _get_conn()
        try:
            existing = get_fields(conn)
        finally:
            conn.close()
        if any(f.field_type == "file" for f in existing):
            return HTMLResponse("Only one CV file field is allowed", status_code=400)

    conn = _get_conn()
    try:
        field = add_field(conn, field_type=field_type)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/field_row.html",
        {"field": field},
    )


@datos_router.post("/datos/fields/remove/{field_id}", response_class=HTMLResponse)
async def datos_fields_remove(request: Request, field_id: int) -> HTMLResponse:
    """Remove a field by id and return updated panel."""
    conn = _get_conn()
    try:
        remove_field(conn, field_id)
        fields = get_fields(conn)
        cv = get_cv(conn)
        platforms = get_platforms(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/panel.html",
        {"fields": fields, "cv": cv, "platforms": platforms},
    )


# -- CV ----------------------------------------------------------------------


@datos_router.get("/datos/cv", response_class=HTMLResponse)
async def datos_cv(request: Request) -> HTMLResponse:
    """CV section partial."""
    conn = _get_conn()
    cv = get_cv(conn)
    conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/cv_section.html",
        {"cv": cv},
    )


@datos_router.post("/datos/cv/upload", response_class=HTMLResponse)
async def datos_cv_upload(
    request: Request,
    file: UploadFile = File(...),
) -> HTMLResponse:
    """Upload a PDF CV file."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return HTMLResponse("Only PDF files are accepted", status_code=400)

    # Ensure CV directory exists
    os.makedirs(str(CV_DIR), exist_ok=True)

    # Generate UUID-based filename
    file_uuid = str(uuid.uuid4())
    disk_path = CV_DIR / f"{file_uuid}.pdf"

    # Save to disk
    content = await file.read()
    MAX_CV_SIZE = 10 * 1024 * 1024  # 10MB
    if len(content) > MAX_CV_SIZE:
        raise HTTPException(status_code=413, detail="CV file exceeds 10MB limit")
    with open(str(disk_path), "wb") as f:
        f.write(content)

    # Save to DB
    conn = _get_conn()
    try:
        save_cv(conn, file_uuid, file.filename, str(disk_path))
        cv = get_cv(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request, "partials/datos/cv_section.html",
        {"cv": cv},
    )


@datos_router.post("/datos/cv/delete", response_class=HTMLResponse)
async def datos_cv_delete(request: Request) -> HTMLResponse:
    """Delete the CV file and record."""
    conn = _get_conn()
    try:
        cv = get_cv(conn)
        if cv and cv.file_path:
            # Remove file from disk
            try:
                os.remove(cv.file_path)
            except FileNotFoundError:
                pass
        delete_cv(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request, "partials/datos/cv_section.html",
        {"cv": None},
    )


@datos_router.get("/datos/cv/preview")
async def datos_cv_preview(request: Request):
    """Serve the CV PDF file for preview."""
    conn = _get_conn()
    cv = get_cv(conn)
    conn.close()

    if cv is None or not cv.file_path:
        return HTMLResponse("No CV found", status_code=404)

    if not os.path.exists(cv.file_path):
        return HTMLResponse("File not found", status_code=404)

    from fastapi.responses import FileResponse
    return FileResponse(cv.file_path, media_type="application/pdf")


# -- Platforms ----------------------------------------------------------------


@datos_router.get("/datos/platforms", response_class=HTMLResponse)
async def datos_platforms(request: Request) -> HTMLResponse:
    """Platform list partial."""
    conn = _get_conn()
    platforms = get_platforms(conn)
    conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/platforms.html",
        {"platforms": platforms},
    )


@datos_router.post("/datos/platforms/add", response_class=HTMLResponse)
async def datos_platforms_add(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
) -> HTMLResponse:
    """Add a new platform."""
    # Validate URL format
    if not (url.startswith("http://") or url.startswith("https://")):
        return HTMLResponse("Invalid URL format", status_code=400)
    if not _URL_RE.match(url):
        return HTMLResponse("Invalid URL format", status_code=400)

    conn = _get_conn()
    try:
        add_platform(conn, name, url)
    except Exception:
        return HTMLResponse("Platform already exists", status_code=400)
    finally:
        platforms = get_platforms(conn)
        conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/platforms.html",
        {"platforms": platforms},
    )


@datos_router.post("/datos/platforms/remove/{platform_id}", response_class=HTMLResponse)
async def datos_platforms_remove(
    request: Request, platform_id: int,
) -> HTMLResponse:
    """Remove a platform by id."""
    conn = _get_conn()
    try:
        remove_platform(conn, platform_id)
        platforms = get_platforms(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/platforms.html",
        {"platforms": platforms},
    )
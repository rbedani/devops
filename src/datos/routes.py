"""FastAPI routes for the datos module — profile fields, CV.

All routes return HTMX-compatible HTML partials.
The scan platform routes have been moved to src.scan.routes as part of
the 5-layer architecture extraction.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from starlette.datastructures import FormData

from src.core.config.settings import CV_DIR as _CORE_CV_DIR
from src.core.config.settings import DB_PATH as _CORE_DB_PATH
from src.datos.store import (
    add_field,
    delete_cv,
    get_connection,
    get_cv,
    get_fields,
    remove_field,
    save_cv,
    save_fields,
)

# -- Paths -------------------------------------------------------------------

TEMPLATE_DIR = Path(__file__).parent.parent / "dashboard" / "templates"
CV_DIR = _CORE_CV_DIR

# -- Templates ---------------------------------------------------------------

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# -- Router ------------------------------------------------------------------

datos_router = APIRouter(tags=["datos"])

# Make DB_PATH patchable (same as server.py pattern)
DB_PATH: str = str(_CORE_DB_PATH)

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

_FIELD_PREFIX_RE = re.compile(r"^field_(\d+)_(id|type|name|value)$")


def _parse_flat_form_fields(form: FormData) -> list[dict[str, Any]]:
    """Convert flat HTMX form fields (field_1_id, field_1_name, ...) into
    the structured format expected by save_fields."""
    fields: dict[int, dict[str, Any]] = {}
    for key in form:
        m = _FIELD_PREFIX_RE.match(key)
        if not m:
            continue
        field_id = int(m.group(1))
        attr = m.group(2)
        if field_id not in fields:
            fields[field_id] = {
                "id": field_id, "name": "", "field_type": "text",
                "value": "", "position": 0,
            }
        value = form[key]
        if attr == "id":
            fields[field_id]["id"] = int(value)
        elif attr == "type":
            fields[field_id]["field_type"] = value
        else:
            fields[field_id][attr] = value
    return list(fields.values())


def _validate_field_value(field_type: str, value: str) -> str | None:
    """Return an error message if the value is invalid for the given type, or None."""
    if not value:
        return None  # empty is OK (optional field)

    if field_type == "numeric":
        try:
            float(value)
        except ValueError:
            return "Value must be a number for numeric field"
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
    conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/panel.html",
        {"fields": fields, "cv": cv},
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
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        fields_data = _parse_flat_form_fields(form)
    else:
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
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/panel.html",
        {"fields": fields, "cv": cv},
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
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/datos/panel.html",
        {"fields": fields, "cv": cv},
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
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")
    content = await file.read()
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


# ===========================================================================
# CLEAN — eliminar datos personales
# ===========================================================================


@datos_router.post("/datos/clean", response_class=HTMLResponse)
async def datos_clean(request: Request) -> HTMLResponse:
    """Delete ALL personal data: profile fields, CV files, and CV files on disk.

    This is the "clean personal data" button in Settings.
    After deletion the datos tables are empty and the CV directory is cleared.
    """
    conn = _get_conn()
    try:
        # 1. Delete CV files from disk first
        cv = get_cv(conn)
        if cv and cv.file_path:
            try:
                if os.path.isfile(cv.file_path):
                    os.remove(cv.file_path)
                # Also remove the parent CV directory tree if it exists
                cv_dir = Path(cv.file_path).parent
                if cv_dir.exists() and cv_dir.is_dir():
                    shutil.rmtree(str(cv_dir), ignore_errors=True)
            except (OSError, PermissionError):
                pass

        # 2. Wipe CV directory entirely
        cv_dir_path = Path(str(CV_DIR))
        if cv_dir_path.exists():
            shutil.rmtree(str(cv_dir_path), ignore_errors=True)

        # 3. Delete all profile_fields and cv_files
        conn.execute("DELETE FROM profile_fields")
        conn.execute("DELETE FROM cv_files")
        conn.commit()
    finally:
        conn.close()

    return templates.TemplateResponse(
        request, "settings.html",
        {"request": request, "cleaned": "datos"},
    )
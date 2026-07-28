"""FastAPI dashboard server — app factory.

Assembles the application: creates the FastAPI instance, mounts static files,
registers all routers (STATUS, SCAN, DATA, API), and sets up lifespan
migrations.

The /apply/auto route now lives in src/api/routes.py (moved in Phase 4).
Templates remain at src/dashboard/templates/ (shared across modules).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.core.config.settings import DB_PATH as _CORE_DB_PATH
from src.core.config.settings import PROJECT_ROOT
from src.core.db.database import run_migrations as run_core_migrations
from src.datos.store import run_datos_migration
from src.scan.store import run_scan_migration

# -- Paths -------------------------------------------------------------------

HERE = Path(__file__).parent
TEMPLATE_DIR = HERE / "templates"
STATIC_DIR = HERE / "static"
DB_PATH: str = str(_CORE_DB_PATH)
DEBUG_MODE: bool = os.environ.get("DEBUG_MODE") is not None

# -- Templates ---------------------------------------------------------------
# Kept for backward compatibility with tests that access server.templates

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
        conn.rollback()
    finally:
        conn.close()


# -- Lifespan ----------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run migrations on startup, clean up on shutdown."""
    run_migration(DB_PATH)
    run_core_migrations(DB_PATH)
    run_datos_migration(DB_PATH)
    run_scan_migration(DB_PATH)
    yield


# -- App Factory -------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Mounts static files and includes all module routers.
    Templates remain shared at src/dashboard/templates/.
    """
    app = FastAPI(title="Job Dashboard", lifespan=lifespan)

    # Static files
    static_dir = PROJECT_ROOT / "src" / "dashboard" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Routers (STATUS, SCAN, DATA, API)
    from src.api.routes import router as api_router
    from src.datos.routes import datos_router
    from src.scan.routes import scan_router
    from src.status.routes import status_router

    app.include_router(status_router)
    app.include_router(scan_router)
    app.include_router(datos_router)
    app.include_router(api_router)

    return app


# -- Module-level app for uvicorn compat -------------------------------------

app = create_app()
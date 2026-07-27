"""E2E test server — starts uvicorn with patched DB_PATH.

Usage:
    python3 tests/e2e/run_server.py <db_path> <port>

Patches the DB_PATH module-level constant in all relevant modules
before the app is fully initialized, so the server uses an isolated
temporary database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Must patch BEFORE any project import that reads settings
db_path = sys.argv[1]
port = int(sys.argv[2])

# 1. Patch settings module
import src.core.config.settings as core_settings

core_settings.DB_PATH = db_path
core_settings.CV_DIR = Path(db_path).parent / "cv"

# 2. Patch server module (run_migration reads server.DB_PATH, not settings)
import src.dashboard.server as server

server.DB_PATH = db_path

# 3. Patch status routes
import src.status.routes as status_routes

status_routes.DB_PATH = db_path

# 4. Patch datos routes
import src.datos.routes as datos_routes

datos_routes.DB_PATH = db_path
datos_routes.CV_DIR = Path(db_path).parent / "cv"

# 5. Patch datos store (get_connection reads from core settings)
import src.datos.store as datos_store

datos_store.DB_PATH = db_path  # Actually datos_store uses get_connection(db_path) which reads from core

# 6. Now start uvicorn — the module-level app was already created by imports above
import uvicorn

# Use the server's app directly (already imported)
uvicorn.run(server.app, port=port, host="127.0.0.1", log_level="warning")
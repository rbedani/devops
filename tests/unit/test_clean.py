"""Tests for Clean Status DB and Clean Personal Data buttons in Settings.

Strict TDD: RED tests first (these will fail because production code
still returns HTMLResponse("")), then GREEN implementation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def clean_client(tmp_path: Path):
    """TestClient with status + datos routers mounted, patched DB_PATH.

    Seeds 1 job in jobs table and 1 profile field in profile_fields
    so tests can verify deletion behavior.
    """
    import src.dashboard.server as server
    from src.datos.routes import datos_router
    from src.status.routes import status_router

    db_path = str(tmp_path / "clean_test.db")

    # Run migrations
    server.run_migration(db_path)
    from src.datos.store import run_datos_migration

    run_datos_migration(db_path)

    # Seed data
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (source, title, url, scraped_at) VALUES (?, ?, ?, ?)",
        ("linkedin", "Test Job", "http://x/test", "2026-07-27T00:00:00"),
    )
    conn.execute(
        "INSERT INTO profile_fields (field_type, name, value) "
        "VALUES (?, ?, ?)",
        ("text", "name", "Test User"),
    )
    conn.commit()
    conn.close()

    # Patch DB_PATH and CV_DIR for all modules that use them
    import src.status.routes as status_routes
    import src.datos.routes as datos_routes

    orig_status = status_routes.DB_PATH
    orig_datos = datos_routes.DB_PATH
    orig_server = server.DB_PATH
    orig_cv_dir = datos_routes.CV_DIR
    status_routes.DB_PATH = db_path
    datos_routes.DB_PATH = db_path
    server.DB_PATH = db_path
    datos_routes.CV_DIR = str(tmp_path / "cv")

    # Mount routers if not already mounted
    router_already_mounted = False
    for r in server.app.routes:
        if hasattr(r, "routes"):
            for sub in r.routes:
                if hasattr(sub, "path") and "/clean-db" in sub.path:
                    router_already_mounted = True
                    break
            if router_already_mounted:
                break

    if not router_already_mounted:
        server.app.include_router(status_router)
        server.app.include_router(datos_router)

    try:
        with TestClient(server.app) as c:
            yield c
    finally:
        status_routes.DB_PATH = orig_status
        datos_routes.DB_PATH = orig_datos
        server.DB_PATH = orig_server
        datos_routes.CV_DIR = orig_cv_dir


# =============================================================================
# /clean-db (Status) Tests
# =============================================================================


class TestCleanStatusDB:
    """POST /clean-db — delete all jobs, return rendered settings template."""

    def test_clean_status_db_returns_200(self, clean_client):
        """RED: POST /clean-db should return 200 with HTML content type."""
        response = clean_client.post("/clean-db")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_clean_status_db_renders_settings_template(self, clean_client):
        """RED: response body should contain settings-tab (settings template)."""
        response = clean_client.post("/clean-db")
        assert "settings-tab" in response.text

    def test_clean_status_db_cleaned_flag(self, clean_client):
        """RED: response body should contain 'Status DB cleaned' flash message."""
        response = clean_client.post("/clean-db")
        assert "Status DB cleaned" in response.text

    def test_clean_status_db_deletes_jobs(self, clean_client):
        """RED: after POST /clean-db, the jobs table should be empty."""
        clean_client.post("/clean-db")

        # Verify DB is empty via a GET /table call
        response = clean_client.get("/table")
        assert "Test Job" not in response.text


# =============================================================================
# /datos/clean (Datos) Tests
# =============================================================================


class TestCleanDatos:
    """POST /datos/clean — delete all personal data, return rendered settings template."""

    def test_clean_datos_returns_200(self, clean_client):
        """RED: POST /datos/clean should return 200 with HTML content type."""
        response = clean_client.post("/datos/clean")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_clean_datos_renders_settings_template(self, clean_client):
        """RED: response body should contain settings-tab (settings template)."""
        response = clean_client.post("/datos/clean")
        assert "settings-tab" in response.text

    def test_clean_datos_cleaned_flag(self, clean_client):
        """RED: response body should contain 'Personal data cleaned' flash message."""
        response = clean_client.post("/datos/clean")
        assert "Personal data cleaned" in response.text

    def test_clean_datos_deletes_profile_data(self, clean_client):
        """RED: after POST /datos/clean, profile_fields table should be empty."""
        # First seed profile data via the panel
        clean_client.post("/datos/clean")

        # Verify via GET /datos/fields that profile fields are gone
        response = clean_client.get("/datos/fields")
        # The response should not contain the seeded field's value
        assert "Test User" not in response.text
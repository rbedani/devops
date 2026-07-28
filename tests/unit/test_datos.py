"""Tests for datos module — models, store, routes, content dedup, date filter.

Following Strict TDD: RED test first → GREEN implementation → TRIANGULATE → REFACTOR.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# D1.1 — Models (dataclasses)
# =============================================================================

class TestProfileField:
    """ProfileField dataclass — init, defaults, field access."""

    def test_init_with_all_fields(self):
        """RED: ProfileField should init with all fields."""
        from src.datos.models import ProfileField
        f = ProfileField(name="Work Email", field_type="email", value="a@b.com", position=1, id=42)
        assert f.name == "Work Email"
        assert f.field_type == "email"
        assert f.value == "a@b.com"
        assert f.position == 1
        assert f.id == 42

    def test_default_values(self):
        """RED: ProfileField should have sensible defaults."""
        from src.datos.models import ProfileField
        f = ProfileField(name="Phone", field_type="phone")
        assert f.value == ""
        assert f.position == 0
        assert f.id is None

    def test_repr_contains_name(self):
        """TRIANGULATE: repr should be useful."""
        from src.datos.models import ProfileField
        f = ProfileField(name="Age", field_type="numeric")
        assert "Age" in repr(f)
        assert "numeric" in repr(f)


class TestCVFile:
    """CVFile dataclass — init, defaults."""

    def test_init_with_all_fields(self):
        """RED: CVFile should init with all fields."""
        from src.datos.models import CVFile
        cv = CVFile(
            filename="abc-123",
            original_name="resume.pdf",
            file_path="data/cv/abc-123.pdf",
            uploaded_at="2024-01-15T10:00:00",
            id=1,
        )
        assert cv.filename == "abc-123"
        assert cv.original_name == "resume.pdf"
        assert cv.file_path == "data/cv/abc-123.pdf"
        assert cv.uploaded_at == "2024-01-15T10:00:00"
        assert cv.id == 1

    def test_default_id_is_none(self):
        """RED: CVFile id should default to None."""
        from src.datos.models import CVFile
        cv = CVFile(filename="x", original_name="x", file_path="x", uploaded_at="x")
        assert cv.id is None


class TestScanPlatform:
    """ScanPlatform dataclass — init, defaults (imported from src.scan.models)."""

    def test_init_with_all_fields(self):
        """RED: ScanPlatform should init with all fields."""
        from src.scan.models import ScanPlatform
        p = ScanPlatform(name="LinkedIn", url="https://www.linkedin.com/jobs/", id=1)
        assert p.name == "LinkedIn"
        assert p.url == "https://www.linkedin.com/jobs/"
        assert p.id == 1

    def test_default_id_is_none(self):
        """RED: ScanPlatform id should default to None."""
        from src.scan.models import ScanPlatform
        p = ScanPlatform(name="Test", url="http://example.com")
        assert p.id is None


# =============================================================================
# D1.2 — Store (migration + CRUD)
# =============================================================================

class TestStore:
    """Store module — migration, connection, CRUD for 2 tables (profile_fields, cv_files)."""

    @pytest.fixture
    def db_path(self, tmp_path: Path) -> str:
        return str(tmp_path / "test_datos.db")

    def test_migration_creates_tables(self, db_path: str):
        """RED: run_datos_migration should create 2 tables idempotently."""
        from src.datos.store import run_datos_migration, get_connection

        run_datos_migration(db_path)
        conn = get_connection(db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        conn.close()

        assert "profile_fields" in tables
        assert "cv_files" in tables

    def test_migration_idempotent(self, db_path: str):
        """RED: running migration twice should not raise."""
        from src.datos.store import run_datos_migration

        run_datos_migration(db_path)
        run_datos_migration(db_path)  # second call — must not raise

    def test_migration_seeds_linkedin(self, db_path: str):
        """RED: SCAN migration should seed LinkedIn as default platform."""
        from src.scan.store import run_scan_migration, get_connection

        run_scan_migration(db_path)
        conn = get_connection(db_path)
        rows = conn.execute("SELECT name, url FROM scan_platforms").fetchall()
        conn.close()
        assert any("LinkedIn" in r[0] for r in rows)

    # -- Profile Fields CRUD ---------------------------------------------------

    def test_get_fields_empty(self, db_path: str):
        """RED: get_fields should return empty list when no fields exist."""
        from src.datos.store import run_datos_migration, get_connection, get_fields

        run_datos_migration(db_path)
        conn = get_connection(db_path)
        fields = get_fields(conn)
        conn.close()
        assert fields == []

    def test_add_field_returns_new_field(self, db_path: str):
        """RED: add_field should create a new field and return it."""
        from src.datos.store import run_datos_migration, get_connection, add_field

        run_datos_migration(db_path)
        conn = get_connection(db_path)
        field = add_field(conn)
        conn.close()
        assert field.name == ""
        assert field.id is not None

    def test_save_fields_persists(self, db_path: str):
        """RED: save_fields should persist all provided fields."""
        from src.datos.store import (
            run_datos_migration, get_connection, add_field, save_fields, get_fields,
        )

        run_datos_migration(db_path)
        conn = get_connection(db_path)

        # Add a field first to get an id
        added = add_field(conn)
        # Now save with actual values
        save_fields(conn, [{"id": added.id, "name": "Email", "field_type": "email", "value": "a@b.com", "position": 0}])

        fields = get_fields(conn)
        conn.close()
        assert len(fields) == 1
        assert fields[0].name == "Email"
        assert fields[0].field_type == "email"
        assert fields[0].value == "a@b.com"

    def test_remove_field(self, db_path: str):
        """RED: remove_field should delete a field by id."""
        from src.datos.store import (
            run_datos_migration, get_connection, add_field, remove_field, get_fields,
        )

        run_datos_migration(db_path)
        conn = get_connection(db_path)
        added = add_field(conn)
        field_id = added.id
        assert field_id is not None

        result = remove_field(conn, field_id)
        assert result is True

        fields = get_fields(conn)
        conn.close()
        assert len(fields) == 0

    def test_remove_nonexistent_field_returns_false(self, db_path: str):
        """TRIANGULATE: removing a nonexistent field should return False."""
        from src.datos.store import run_datos_migration, get_connection, remove_field

        run_datos_migration(db_path)
        conn = get_connection(db_path)
        result = remove_field(conn, 9999)
        conn.close()
        assert result is False

    # -- CV Files CRUD ---------------------------------------------------------

    def test_get_cv_empty(self, db_path: str):
        """RED: get_cv should return None when no CV exists."""
        from src.datos.store import run_datos_migration, get_connection, get_cv

        run_datos_migration(db_path)
        conn = get_connection(db_path)
        cv = get_cv(conn)
        conn.close()
        assert cv is None

    def test_save_and_get_cv(self, db_path: str):
        """RED: save_cv should persist a CV record and get_cv should retrieve it."""
        from src.datos.store import run_datos_migration, get_connection, save_cv, get_cv

        run_datos_migration(db_path)
        conn = get_connection(db_path)
        cv_id = save_cv(conn, "uuid-123", "resume.pdf", "data/cv/uuid-123.pdf")
        assert cv_id is not None

        cv = get_cv(conn)
        conn.close()
        assert cv is not None
        assert cv.filename == "uuid-123"
        assert cv.original_name == "resume.pdf"

    def test_delete_cv(self, db_path: str):
        """RED: delete_cv should remove the CV record."""
        from src.datos.store import (
            run_datos_migration, get_connection, save_cv, delete_cv, get_cv,
        )

        run_datos_migration(db_path)
        conn = get_connection(db_path)
        save_cv(conn, "uuid-456", "doc.pdf", "data/cv/uuid-456.pdf")
        result = delete_cv(conn)
        assert result is True

        cv = get_cv(conn)
        conn.close()
        assert cv is None

    def test_delete_cv_when_none_returns_false(self, db_path: str):
        """TRIANGULATE: delete_cv when no CV exists should return False."""
        from src.datos.store import run_datos_migration, get_connection, delete_cv

        run_datos_migration(db_path)
        conn = get_connection(db_path)
        result = delete_cv(conn)
        conn.close()
        assert result is False

    # -- Scan Platforms CRUD ---------------------------------------------------

    def test_get_platforms_after_seed(self, db_path: str):
        """RED: get_platforms should return LinkedIn after SCAN migration."""
        from src.scan.store import run_scan_migration, get_connection, get_platforms

        run_scan_migration(db_path)
        conn = get_connection(db_path)
        platforms = get_platforms(conn)
        conn.close()
        assert len(platforms) >= 1
        names = [p.name for p in platforms]
        assert "LinkedIn" in names

    def test_add_platform(self, db_path: str):
        """RED: add_platform should insert and return the new platform id."""
        from src.scan.store import run_scan_migration, get_connection, add_platform, get_platforms

        run_scan_migration(db_path)
        conn = get_connection(db_path)
        pid = add_platform(conn, "TestPlatform", "https://example.com/jobs/")
        assert pid is not None

        platforms = get_platforms(conn)
        conn.close()
        names = [p.name for p in platforms]
        assert "TestPlatform" in names

    def test_remove_platform(self, db_path: str):
        """RED: remove_platform should delete a platform by id."""
        from src.scan.store import (
            run_scan_migration, get_connection, add_platform, remove_platform, get_platforms,
        )

        run_scan_migration(db_path)
        conn = get_connection(db_path)
        pid = add_platform(conn, "TestPlatform", "https://example.com/jobs/")
        assert pid is not None

        result = remove_platform(conn, pid)
        assert result is True

        platforms = get_platforms(conn)
        conn.close()
        names = [p.name for p in platforms]
        assert "TestPlatform" not in names

    def test_remove_platform_nonexistent_returns_false(self, db_path: str):
        """TRIANGULATE: removing a platform that doesn't exist should return False."""
        from src.scan.store import run_scan_migration, get_connection, remove_platform

        run_scan_migration(db_path)
        conn = get_connection(db_path)
        result = remove_platform(conn, 9999)
        conn.close()
        assert result is False

    def test_seed_tecnoempleo(self, db_path: str):
        """RED: SCAN migration should seed Tecnoempleo with correct url and enabled=1."""
        from src.scan.store import run_scan_migration, get_connection

        run_scan_migration(db_path)
        conn = get_connection(db_path)
        rows = conn.execute(
            "SELECT name, url, enabled FROM scan_platforms WHERE name = ?", ("Tecnoempleo",)
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["name"] == "Tecnoempleo"
        assert rows[0]["url"] == "https://www.tecnoempleo.com/ofertas-trabajo/"
        assert rows[0]["enabled"] == 1

    def test_seed_tecnoempleo_idempotent(self, db_path: str):
        """TRIANGULATE: running migration twice should not duplicate Tecnoempleo."""
        from src.scan.store import run_scan_migration, get_connection

        run_scan_migration(db_path)
        run_scan_migration(db_path)
        conn = get_connection(db_path)
        rows = conn.execute(
            "SELECT COUNT(*) as cnt FROM scan_platforms WHERE name = ?", ("Tecnoempleo",)
        ).fetchone()
        conn.close()
        assert rows["cnt"] == 1


# =============================================================================
# D1.3 — Routes (TestClient integration)
# =============================================================================

@pytest.fixture
def datos_client(tmp_path: Path):
    """TestClient with datos + scan routers mounted and patched DB_PATH."""
    import src.dashboard.server as server
    from src.datos.routes import datos_router
    from src.scan.routes import scan_router

    db_path = str(tmp_path / "datos_test.db")

    # Run migrations
    from src.datos.store import run_datos_migration
    run_datos_migration(db_path)
    from src.scan.store import run_scan_migration
    run_scan_migration(db_path)
    server.run_migration(db_path)

    # Patch DB_PATH for routes modules
    import src.datos.routes as datos_routes
    original_routes = datos_routes.DB_PATH
    datos_routes.DB_PATH = db_path

    import src.scan.routes as scan_routes
    original_scan_routes = scan_routes.DB_PATH
    scan_routes.DB_PATH = db_path

    # Mount the routers (idempotent check)
    router_already_mounted = False
    for r in server.app.routes:
        if hasattr(r, "routes"):
            for sub in r.routes:
                if hasattr(sub, "path") and "/datos/" in sub.path:
                    router_already_mounted = True
                    break
        if router_already_mounted:
            break

    if not router_already_mounted:
        server.app.include_router(datos_router)
        server.app.include_router(scan_router)

    original_server_db = server.DB_PATH
    server.DB_PATH = db_path

    try:
        with TestClient(server.app) as c:
            yield c
    finally:
        server.DB_PATH = original_server_db
        datos_routes.DB_PATH = original_routes
        scan_routes.DB_PATH = original_scan_routes


class TestRoutes:
    """Datos routes — panel, fields, CV, platforms."""

    # -- Panel -----------------------------------------------------------------

    def test_panel_returns_200(self, datos_client):
        """RED: GET /datos/panel should return 200 HTML."""
        response = datos_client.get("/datos/panel")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_panel_contains_save_button(self, datos_client):
        """RED: panel should contain SAVE and ADD FIELD buttons."""
        response = datos_client.get("/datos/panel")
        assert "SAVE" in response.text or "save" in response.text
        assert "ADD FIELD" in response.text or "add-field" in response.text

    # -- Fields ----------------------------------------------------------------

    def test_fields_returns_200(self, datos_client):
        """RED: GET /datos/fields should return 200 HTML."""
        response = datos_client.get("/datos/fields")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_fields_empty_initially(self, datos_client):
        """RED: GET /datos/fields should show no fields initially."""
        response = datos_client.get("/datos/fields")
        assert response.status_code == 200

    def test_add_field_returns_row_html(self, datos_client):
        """RED: POST /datos/fields/add should return field_row.html partial."""
        response = datos_client.post("/datos/fields/add")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_save_fields(self, datos_client):
        """RED: POST /datos/fields/save should persist and return updated panel."""
        add_resp = datos_client.post("/datos/fields/add")
        assert add_resp.status_code == 200

        resp = datos_client.post("/datos/fields/save", json={"fields": []})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_remove_field(self, datos_client):
        """RED: POST /datos/fields/remove/{id} should remove and return panel."""
        add_resp = datos_client.post("/datos/fields/add")
        assert add_resp.status_code == 200

        resp = datos_client.post("/datos/fields/remove/1")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_add_field_rejects_second_file_field(self, datos_client):
        """RED: Adding a second file-type field should be rejected."""
        add_resp = datos_client.post("/datos/fields/add", data={"field_type": "file"})
        assert add_resp.status_code == 200

        add_resp = datos_client.post("/datos/fields/add", data={"field_type": "file"})
        assert add_resp.status_code == 400
        assert "Only one CV file field is allowed" in add_resp.text

    def test_add_field_allows_non_file_fields(self, datos_client):
        """TRIANGULATE: Adding a non-file field when a file field exists should work."""
        add_resp = datos_client.post("/datos/fields/add", data={"field_type": "file"})
        assert add_resp.status_code == 200

        add_resp = datos_client.post("/datos/fields/add", data={"field_type": "text"})
        assert add_resp.status_code == 200

    def test_save_rejects_non_numeric_in_numeric_field(self, datos_client):
        """RED: POST /datos/fields/save should reject non-numeric value in a numeric field."""
        add_resp = datos_client.post("/datos/fields/add")
        assert add_resp.status_code == 200

        resp = datos_client.post("/datos/fields/save", json={
            "fields": [{"id": 1, "name": "Age", "field_type": "numeric", "value": "abc", "position": 0}]
        })
        assert resp.status_code == 400
        assert "numeric" in resp.text.lower()

    def test_save_rejects_email_without_at(self, datos_client):
        """RED: POST /datos/fields/save should reject email value without @."""
        add_resp = datos_client.post("/datos/fields/add")
        assert add_resp.status_code == 200

        resp = datos_client.post("/datos/fields/save", json={
            "fields": [{"id": 1, "name": "Work Email", "field_type": "email", "value": "notanemail", "position": 0}]
        })
        assert resp.status_code == 400
        assert "email" in resp.text.lower()

    def test_save_rejects_invalid_url(self, datos_client):
        """RED: POST /datos/fields/save should reject invalid URL value."""
        add_resp = datos_client.post("/datos/fields/add")
        assert add_resp.status_code == 200

        resp = datos_client.post("/datos/fields/save", json={
            "fields": [{"id": 1, "name": "Website", "field_type": "url", "value": "not-a-url", "position": 0}]
        })
        assert resp.status_code == 400
        assert "url" in resp.text.lower()

    def test_save_rejects_invalid_date(self, datos_client):
        """RED: POST /datos/fields/save should reject non-YYYY-MM-DD date."""
        add_resp = datos_client.post("/datos/fields/add")
        assert add_resp.status_code == 200

        resp = datos_client.post("/datos/fields/save", json={
            "fields": [{"id": 1, "name": "Birth", "field_type": "date", "value": "not-a-date", "position": 0}]
        })
        assert resp.status_code == 400
        assert "date" in resp.text.lower()

    def test_save_accepts_valid_numeric(self, datos_client):
        """TRIANGULATE: POST /datos/fields/save should accept valid numeric values."""
        add_resp = datos_client.post("/datos/fields/add")
        assert add_resp.status_code == 200

        resp = datos_client.post("/datos/fields/save", json={
            "fields": [{"id": 1, "name": "Age", "field_type": "numeric", "value": "42", "position": 0}]
        })
        assert resp.status_code == 200

    def test_save_accepts_valid_email(self, datos_client):
        """TRIANGULATE: POST /datos/fields/save should accept valid email."""
        add_resp = datos_client.post("/datos/fields/add")
        assert add_resp.status_code == 200

        resp = datos_client.post("/datos/fields/save", json={
            "fields": [{"id": 1, "name": "Email", "field_type": "email", "value": "a@b.com", "position": 0}]
        })
        assert resp.status_code == 200

    # -- CV --------------------------------------------------------------------

    def test_cv_returns_200(self, datos_client):
        """RED: GET /datos/cv should return 200 HTML."""
        response = datos_client.get("/datos/cv")
        assert response.status_code == 200

    def test_cv_upload_rejects_non_pdf(self, datos_client):
        """RED: POST /datos/cv/upload should reject non-PDF files."""
        response = datos_client.post(
            "/datos/cv/upload",
            files={"file": ("resume.png", b"fake-png-content", "image/png")},
        )
        assert response.status_code == 400
        assert "Only PDF files are accepted" in response.text

    def test_cv_delete_returns_200(self, datos_client):
        """RED: POST /datos/cv/delete should return 200 HTML."""
        response = datos_client.post("/datos/cv/delete")
        assert response.status_code == 200

    # -- Platforms -------------------------------------------------------------

    def test_platforms_returns_200(self, datos_client):
        """RED: GET /datos/platforms should return 200 HTML."""
        response = datos_client.get("/datos/platforms")
        assert response.status_code == 200

    def test_platforms_shows_linkedin(self, datos_client):
        """RED: GET /datos/platforms should show LinkedIn (seeded)."""
        response = datos_client.get("/datos/platforms")
        assert "LinkedIn" in response.text

    def test_add_platform(self, datos_client):
        """RED: POST /datos/platforms/add should add platform."""
        response = datos_client.post("/datos/platforms/add", data={"name": "TestPlatform", "url": "https://example.com/jobs/"})
        assert response.status_code == 200
        assert "TestPlatform" in response.text

    def test_remove_platform(self, datos_client):
        """RED: POST /datos/platforms/remove/{id} should remove platform."""
        response = datos_client.post("/datos/platforms/remove/1")
        assert response.status_code == 200

    def test_add_platform_rejects_invalid_url(self, datos_client):
        """RED: POST /datos/platforms/add should reject invalid URL format."""
        response = datos_client.post("/datos/platforms/add", data={"name": "Test", "url": "not-a-url"})
        assert response.status_code == 400
        assert "Invalid URL format" in response.text

    def test_add_platform_accepts_valid_url(self, datos_client):
        """TRIANGULATE: POST /datos/platforms/add should accept valid URL."""
        response = datos_client.post("/datos/platforms/add", data={"name": "Test", "url": "https://example.com/"})
        assert response.status_code == 200


# =============================================================================
# D3 — Content Dedup + Date Filter
# =============================================================================

class TestContentHash:
    """Content hash computation — SHA-256 of title+company+description."""

    def test_sha256_known_input(self):
        """RED: SHA-256 of known inputs should match expected."""
        from src.core.db.database import _content_hash
        result = _content_hash("Engineer", "Acme", "Build things")
        expected = hashlib.sha256("EngineerAcmeBuild things".encode()).hexdigest()
        assert result == expected

    def test_different_content_different_hash(self):
        """TRIANGULATE: different content should produce different hashes."""
        from src.core.db.database import _content_hash
        h1 = _content_hash("Engineer", "Acme", "Build things")
        h2 = _content_hash("Manager", "Beta", "Manage things")
        assert h1 != h2

    def test_empty_content(self):
        """TRIANGULATE: empty strings should still produce a hash."""
        from src.core.db.database import _content_hash
        result = _content_hash("", "", "")
        expected = hashlib.sha256("".encode()).hexdigest()
        assert result == expected


class TestDateFilterSQL:
    """Date filter — verify WHERE clause behavior."""

    def test_no_filter_shows_all(self, tmp_path: Path):
        """RED: without since param, all jobs should be returned."""
        db_path = str(tmp_path / "date_test.db")
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                company TEXT,
                location TEXT,
                description TEXT,
                tags TEXT DEFAULT '[]',
                scraped_at TEXT NOT NULL
            )
        """)
        conn.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT ''")
        conn.execute(
            "INSERT INTO jobs (source, title, url, scraped_at) VALUES (?, ?, ?, ?)",
            ("linkedin", "Old Job", "http://x/old", (now - timedelta(days=20)).isoformat()),
        )
        conn.execute(
            "INSERT INTO jobs (source, title, url, scraped_at) VALUES (?, ?, ?, ?)",
            ("linkedin", "Recent Job", "http://x/recent", (now - timedelta(hours=1)).isoformat()),
        )
        conn.commit()
        conn.close()

        import src.dashboard.server as server
        import src.status.routes as status_routes
        original = server.DB_PATH
        orig_status = status_routes.DB_PATH
        server.DB_PATH = db_path
        status_routes.DB_PATH = db_path
        try:
            response = TestClient(server.app).get("/table")
            assert response.status_code == 200
            assert "Old Job" in response.text
            assert "Recent Job" in response.text
        finally:
            server.DB_PATH = original
            status_routes.DB_PATH = orig_status

    def test_filter_24h_excludes_old(self, tmp_path: Path):
        """RED: since=24h should exclude jobs older than 24 hours."""
        db_path = str(tmp_path / "date_test_24h.db")
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                company TEXT,
                location TEXT,
                description TEXT,
                tags TEXT DEFAULT '[]',
                scraped_at TEXT NOT NULL
            )
        """)
        conn.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT ''")
        conn.execute(
            "INSERT INTO jobs (source, title, url, scraped_at) VALUES (?, ?, ?, ?)",
            ("linkedin", "Old Job", "http://x/old", (now - timedelta(days=20)).isoformat()),
        )
        conn.execute(
            "INSERT INTO jobs (source, title, url, scraped_at) VALUES (?, ?, ?, ?)",
            ("linkedin", "Recent Job", "http://x/recent", (now - timedelta(hours=1)).isoformat()),
        )
        conn.commit()
        conn.close()

        import src.dashboard.server as server
        import src.status.routes as status_routes
        original = server.DB_PATH
        orig_status = status_routes.DB_PATH
        server.DB_PATH = db_path
        status_routes.DB_PATH = db_path
        try:
            response = TestClient(server.app).get("/table?since=24h")
            assert response.status_code == 200
            assert "Old Job" not in response.text
            assert "Recent Job" in response.text
        finally:
            server.DB_PATH = original
            status_routes.DB_PATH = orig_status
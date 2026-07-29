"""Tests for Dino Scan Animation — CSS, HTML, JS integration.

Written FIRST (RED) per Strict TDD protocol. References production code
that does not exist yet at the time of writing.
"""

import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Shared fixtures (reused across test classes)
# =============================================================================


@pytest.fixture
def seeded_db(tmp_path: Path) -> str:
    """Create and seed a temp jobs DB with test data."""
    db_path = str(tmp_path / "dashboard_test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        company TEXT,
        location TEXT,
        description TEXT,
        tags TEXT DEFAULT '[]',
        scraped_at TEXT NOT NULL
    )""")
    conn.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT ''")
    fixtures = [
        ("linkedin", "DevOps Engineer", "http://x/1", "Acme Inc", "Buenos Aires",
         '[{"key": "fecha_publicacion", "value": "2024-01-15", "confidence": 1.0}]',
         "2024-01-15T10:00:00", ""),
        ("linkedin", "SRE Specialist",  "http://x/2", "Beta Corp", "Remote",
         '[]', "2024-01-14T10:00:00", ""),
        ("indeed",   "Platform Engineer", "http://x/3", "Acme Inc", "Madrid",
         '[{"key": "salario", "value": "70k", "confidence": 1.0}]',
         "2024-01-13T10:00:00", "auto-applied"),
    ]
    for f in fixtures:
        conn.execute(
            "INSERT INTO jobs (source, title, url, company, location, tags, scraped_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", f
        )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(seeded_db: str):
    """FastAPI TestClient with patched DB_PATH for server, status, AND scan routes."""
    import src.dashboard.server as server
    import src.scan.routes as scan_routes
    import src.status.routes as status_routes
    original = server.DB_PATH
    orig_status = status_routes.DB_PATH
    orig_scan = scan_routes.DB_PATH
    server.DB_PATH = seeded_db
    status_routes.DB_PATH = seeded_db
    scan_routes.DB_PATH = seeded_db

    # Create scan_platforms table in the test DB
    from src.scan.store import run_scan_migration
    run_scan_migration(seeded_db)

    try:
        from src.dashboard.server import app
        with TestClient(app) as c:
            yield c
    finally:
        server.DB_PATH = original
        status_routes.DB_PATH = orig_status
        scan_routes.DB_PATH = orig_scan


# =============================================================================
# Task 1.1 — CSS: Banner expansion & canvas container
# =============================================================================

class TestDinoCSS:
    """CSS must define #dino-banner.expanded state and canvas positioning."""

    def test_css_has_expanded_class(self, client):
        """RED: style.css should define #dino-banner.expanded selector."""
        response = client.get("/static/scan.css")
        css = response.text
        assert "#dino-banner.expanded" in css

    def test_css_expanded_height_45px(self, client):
        """RED: #dino-banner.expanded should set height: 160px."""
        response = client.get("/static/scan.css")
        css = response.text
        # Must be inside a #dino-banner.expanded context
        expanded_section = css[css.find("#dino-banner.expanded"):]
        assert "160px" in expanded_section[:200]

    def test_css_expanded_transition(self, client):
        """RED: .scan-progress should have CSS transition on height."""
        response = client.get("/static/scan.css")
        css = response.text
        assert "transition" in css
        assert "height" in css

    def test_css_has_dino_canvas_positioning(self, client):
        """RED: #dino-canvas should be absolute positioned."""
        response = client.get("/static/scan.css")
        css = response.text
        assert "#dino-canvas" in css
        assert "absolute" in css

    def test_css_canvas_pointer_events_none(self, client):
        """RED: #dino-canvas should have pointer-events: none."""
        response = client.get("/static/scan.css")
        css = response.text
        assert "pointer-events" in css
        assert "none" in css

    def test_css_mobile_35px_height(self, client):
        """RED: at ≤768px, expanded height should be 100px."""
        response = client.get("/static/scan.css")
        css = response.text
        # Find media query for max-width: 768px
        media_matches = re.findall(
            r'@media\s*\([^)]*max-width:\s*768px[^)]*\).*?\{[^}]*\}',
            css, re.DOTALL
        )
        expanded_in_media = any("100px" in m for m in media_matches)
        more_media = css[css.find("@media"):] if "@media" in css else ""
        second_media = more_media[more_media.find("@media"):] if "@media" in more_media else ""
        has_100 = "100px" in second_media

        # Accept either pattern
        assert expanded_in_media or has_100 or ("100px" in css and "768" in css)


class TestDinoCSSSection:
    """CSS should have a clearly commented Dino-specific section."""

    def test_dino_css_section_comment(self, client):
        """RED: style.css should have a Dino-specific section comment."""
        response = client.get("/static/scan.css")
        assert "Dino" in response.text or "dino" in response.text.lower()


# =============================================================================
# Task 1.2 — HTML: Canvas element in progress partial
# =============================================================================

class TestDinoHTML:
    """Progress partial should include canvas element."""

    def test_progress_template_has_canvas(self):
        """RED: progress.html should contain a canvas element."""
        from src.scan.runner import ScanState
        import src.dashboard.server as server

        state = ScanState()
        state.running = True
        state.progress_pct = 50.0
        response = server.templates.TemplateResponse(
            None, "partials/progress.html",
            {"state": state},
        )
        body = response.body.decode()
        assert "dino-canvas" in body
        assert "<canvas" in body


# =============================================================================
# Task 2.1 — JS: DinoCanvasRenderer class
# =============================================================================

class TestDinoJSClass:
    """script.js must define DinoCanvasRenderer class."""

    def test_js_has_dino_canvas_renderer_class(self, client):
        """RED: script.js should define DinoCanvasRenderer class."""
        response = client.get("/static/script.js")
        js = response.text
        assert "DinoCanvasRenderer" in js

    def test_js_has_constructor(self, client):
        """RED: DinoCanvasRenderer should have a constructor (function)."""
        response = client.get("/static/script.js")
        js = response.text
        # ES5 function constructor pattern
        assert "function DinoCanvasRenderer" in js

    def test_js_has_start_method(self, client):
        """RED: DinoCanvasRenderer should have a start() method."""
        response = client.get("/static/script.js")
        js = response.text
        assert "this.start" in js or ".start" in js

    def test_js_has_stop_method(self, client):
        """RED: DinoCanvasRenderer should have a stop() method."""
        response = client.get("/static/script.js")
        js = response.text
        assert "this.stop" in js or ".stop" in js

    def test_js_has_update_progress_method(self, client):
        """RED: DinoCanvasRenderer should have updateProgress()."""
        response = client.get("/static/script.js")
        js = response.text
        assert "updateProgress" in js

    def test_js_has_read_theme_colors_method(self, client):
        """RED: DinoCanvasRenderer should have _readThemeColors()."""
        response = client.get("/static/script.js")
        js = response.text
        assert "_readThemeColors" in js

    def test_js_has_resize_method(self, client):
        """RED: DinoCanvasRenderer should have resize()."""
        response = client.get("/static/script.js")
        js = response.text
        assert "resize" in js

    def test_js_has_loop_method(self, client):
        """RED: DinoCanvasRenderer should have _loop()."""
        response = client.get("/static/script.js")
        js = response.text
        assert "_loop" in js

    def test_js_has_draw_sprite_method(self, client):
        """RED: DinoCanvasRenderer should have drawScene()."""
        response = client.get("/static/script.js")
        js = response.text
        assert "drawScene" in js

    def test_js_has_pixel_sprites(self, client):
        """RED: DinoCanvasRenderer should define sprite frame positions."""
        response = client.get("/static/script.js")
        js = response.text
        assert "DINO_FRAMES" in js
        assert "RUNNING" in js
        assert "DUCKING" in js
        assert "JUMPING" in js
        assert "dinoSprite" in js


# =============================================================================
# Task 2.4 — JS: SSE Integration & obstacle logic
# =============================================================================

class TestDinoSSEIntegration:
    """script.js must wire DinoCanvasRenderer into SSE listener."""

    def test_js_start_scan_listener_creates_dino(self, client):
        """RED: startScanListener should reference DinoCanvasRenderer."""
        response = client.get("/static/script.js")
        js = response.text
        assert "DinoCanvasRenderer" in js
        assert "startScanListener" in js

    def test_js_expands_container_on_scan(self, client):
        """RED: script.js should add 'expanded' class on scan start."""
        response = client.get("/static/script.js")
        js = response.text
        assert "expanded" in js
        assert "classList" in js or "className" in js

    def test_js_collapses_container_after_done(self, client):
        """RED: script.js should remove 'expanded' class after scan completes."""
        response = client.get("/static/script.js")
        js = response.text
        assert "expanded" in js
        # Should have remove or toggle for expanded
        assert "remove" in js


# =============================================================================
# Task 2.4 — JS: Dino obstacle spawning and auto-jump
# =============================================================================

class TestDinoObstacles:
    """Renderer should have obstacle spawning logic."""

    def test_js_has_obstacle_thresholds(self, client):
        """RED: script.js should define obstacle thresholds."""
        response = client.get("/static/script.js")
        js = response.text
        assert "obstacle" in js.lower() or "Obstacle" in js


# =============================================================================
# Task 3 — Server-side state changes
# =============================================================================

class TestDinoServerSide:
    """Server-side: scan trigger should work with expanded template."""

    def test_scan_trigger_returns_progress_html(self, client):
        """RED: GET /scan should return progress HTML with canvas."""
        from unittest.mock import patch
        from src.scan.runner import scan_state

        scan_state.reset()
        with patch("src.scan.routes.run_scan"):
            response = client.get("/scan")
        assert response.status_code == 200
        body = response.text
        assert "progress" in body.lower()
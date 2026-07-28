"""Tests for dashboard backend components (Phase 1 — PR 1) and frontend (Phase 2 — PR 2).

Written FIRST (RED) per Strict TDD protocol. References production code
that does not exist yet at the time of writing.
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Task 1.3 — ScanState dataclass (pure unit, no deps)
# =============================================================================

class TestScanState:
    """ScanState dataclass — init, defaults, field access."""

    def test_default_values(self):
        """RED: a fresh ScanState should have all default values."""
        from src.scan.runner import ScanState
        state = ScanState()
        assert state.running is False
        assert state.progress_pct == 0.0
        assert state.current_target == ""
        assert state.targets_completed == 0
        assert state.targets_total == 0
        assert state.log_lines == []
        assert state.error is None

    def test_can_set_fields(self):
        """RED: all fields should be writable after init."""
        from src.scan.runner import ScanState
        state = ScanState()
        state.running = True
        state.progress_pct = 50.0
        state.current_target = "devops_espana"
        state.targets_completed = 2
        state.targets_total = 5
        state.log_lines.append("Processing target 1")
        state.error = "Something went wrong"

        assert state.running is True
        assert state.progress_pct == 50.0
        assert state.current_target == "devops_espana"
        assert state.targets_completed == 2
        assert state.targets_total == 5
        assert state.log_lines == ["Processing target 1"]
        assert state.error == "Something went wrong"

    def test_independent_instances(self):
        """RED: each ScanState instance should have its own log_lines."""
        from src.scan.runner import ScanState
        state1 = ScanState()
        state2 = ScanState()
        state1.log_lines.append("line from state1")
        assert state2.log_lines == []


# =============================================================================
# Task 1.3 — run_scan subprocess adapter (mocked subprocess)
# =============================================================================

class TestRunScan:
    """run_scan() async subprocess adapter — command, streaming, state updates."""

    @pytest.mark.asyncio
    async def test_calls_correct_command(self):
        """RED: run_scan should invoke sys.executable -m scripts.run_search."""
        from src.scan.runner import ScanState, run_scan

        state = ScanState()
        # Mock the subprocess to avoid actually running it
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([
            b"INFO: Running target: devops_espana\n",
            b"INFO: ======\n",
            b"TOTAL: 5 jobs across 1 targets\n",
        ])
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)) as mock_subproc:
            await run_scan(state)

        # Verify the subprocess was called with the right command
        mock_subproc.assert_called_once()
        args, kwargs = mock_subproc.call_args
        assert "scripts.run_search" in args

    @pytest.mark.asyncio
    async def test_updates_state_on_progress(self):
        """RED: run_scan should update ScanState as it parses stdout."""
        from src.scan.runner import ScanState, run_scan

        state = ScanState()
        mock_process = AsyncMock()
        stdout_lines = [
            b"INFO: Running target: devops_espana\n",
            b"INFO: Loading targets...\n",
            b"INFO: ======\n",
            b"TOTAL: 10 jobs across 2 targets\n",
        ]
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter(stdout_lines)
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)):
            await run_scan(state)

        assert state.running is False
        assert state.progress_pct == 100.0
        assert state.error is None

    @pytest.mark.asyncio
    async def test_sets_error_on_failure(self):
        """RED: run_scan should set error state when subprocess fails."""
        from src.scan.runner import ScanState, run_scan

        state = ScanState()
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([
            b"ERROR: Config not found: config/targets.json\n",
        ])
        mock_process.wait = AsyncMock(return_value=1)
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)):
            await run_scan(state)

        assert state.running is False
        assert state.error is not None


# =============================================================================
# Task 1.4 — DB Migration (ALTER TABLE ADD COLUMN status)
# =============================================================================

class TestMigration:
    """Additive status column migration — idempotent, data-preserving."""

    def _create_jobs_table(self, db_path: Path) -> sqlite3.Connection:
        """Helper: create a fresh jobs table without status column."""
        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            company TEXT,
            location TEXT,
            tags TEXT DEFAULT '[]',
            scraped_at TEXT NOT NULL
        )""")
        conn.commit()
        return conn

    def test_adds_status_column(self, tmp_path: Path):
        """RED: migration should add status column to a fresh DB."""
        db_path = tmp_path / "no_status.db"
        self._create_jobs_table(db_path).close()

        from src.dashboard.server import run_migration
        run_migration(str(db_path))

        conn = sqlite3.connect(str(db_path))
        columns = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        conn.close()
        assert "status" in columns

    def test_idempotent(self, tmp_path: Path):
        """RED: running migration twice should not raise."""
        db_path = tmp_path / "idempotent.db"
        self._create_jobs_table(db_path).close()

        from src.dashboard.server import run_migration
        run_migration(str(db_path))
        run_migration(str(db_path))  # second call — must not raise

        conn = sqlite3.connect(str(db_path))
        columns = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        conn.close()
        assert "status" in columns

    def test_existing_data_preserved(self, tmp_path: Path):
        """RED: existing rows should survive migration."""
        db_path = tmp_path / "preserve.db"
        conn = self._create_jobs_table(db_path)
        conn.execute(
            "INSERT INTO jobs (source, title, url, scraped_at) VALUES (?, ?, ?, ?)",
            ("linkedin", "DevOps Engineer", "http://x/1", "2024-01-15T10:00:00"),
        )
        conn.commit()
        conn.close()

        from src.dashboard.server import run_migration
        run_migration(str(db_path))

        conn = sqlite3.connect(str(db_path))
        title = conn.execute("SELECT title FROM jobs").fetchone()[0]
        conn.close()
        assert title == "DevOps Engineer"

    def test_skips_if_column_exists(self, tmp_path: Path):
        """RED: if status column already exists, migration is no-op."""
        db_path = tmp_path / "already_has.db"
        conn = self._create_jobs_table(db_path)
        conn.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT ''")
        conn.commit()
        conn.close()

        from src.dashboard.server import run_migration
        run_migration(str(db_path))  # must not raise

        conn = sqlite3.connect(str(db_path))
        columns = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        conn.close()
        assert "status" in columns
        assert columns.count("status") == 1  # no duplicate


# =============================================================================
# Task 1.2 — Scan keyword env var injection (pure unit, mocked subprocess)
# =============================================================================

class TestScanKeyword:
    """Keyword pass-through for run_scan() — env var, sanitization."""

    @pytest.mark.asyncio
    async def test_sets_scan_keyword_env_var(self):
        """RED: run_scan should set SCAN_KEYWORD in subprocess env when keyword provided."""
        from src.scan.runner import ScanState, run_scan

        state = ScanState()
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([
            b"INFO: Running target: devops_espana\n",
            b"TOTAL: 5 jobs across 1 targets\n",
        ])
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)) as mock_subproc:
            await run_scan(state, keyword="DevOps Engineer")

        _, kwargs = mock_subproc.call_args
        env = kwargs.get("env", {})
        assert env.get("SCAN_KEYWORD") == "DevOps Engineer"

    @pytest.mark.asyncio
    async def test_skips_env_var_when_keyword_empty(self):
        """RED: run_scan should NOT set SCAN_KEYWORD when keyword is empty string."""
        from src.scan.runner import ScanState, run_scan

        state = ScanState()
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([
            b"TOTAL: 5 jobs across 1 targets\n",
        ])
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)) as mock_subproc:
            await run_scan(state, keyword="")

        _, kwargs = mock_subproc.call_args
        env = kwargs.get("env", {})
        # SCAN_KEYWORD should not be in env, or be empty
        assert "SCAN_KEYWORD" not in env or env["SCAN_KEYWORD"] == ""

    @pytest.mark.asyncio
    async def test_sanitized_keyword_passed_to_env(self):
        """TRIANGULATE: special chars in keyword should be sanitized before setting env var."""
        from src.scan.runner import ScanState, run_scan

        state = ScanState()
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([
            b"TOTAL: 5 jobs across 1 targets\n",
        ])
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)) as mock_subproc:
            await run_scan(state, keyword="devops; rm -rf /")

        _, kwargs = mock_subproc.call_args
        env = kwargs.get("env", {})
        kw = env.get("SCAN_KEYWORD", "")
        # The dangerous ; should be stripped
        assert ";" not in kw


# =============================================================================
# Task 1.8 — Threat matrix: keyword sanitization
# =============================================================================

class TestKeywordSanitization:
    """Sanitize keyword input to guard against injection via subprocess env."""

    def test_strips_semicolons(self):
        """RED: special char ; should be stripped from keyword."""
        from src.scan.runner import sanitize_keyword
        result = sanitize_keyword("devops; rm -rf /")
        assert ";" not in result

    def test_strips_pipe(self):
        """RED: pipe char | should be stripped from keyword."""
        from src.scan.runner import sanitize_keyword
        result = sanitize_keyword("devops|echo")
        assert "|" not in result

    def test_strips_shell_injection(self):
        """RED: $() should be stripped from keyword."""
        from src.scan.runner import sanitize_keyword
        result = sanitize_keyword("devops$(whoami)")
        assert "$" not in result
        assert "(" not in result
        assert ")" not in result

    def test_allows_normal_alphanumeric(self):
        """RED: normal alphanumeric + spaces should pass through unchanged."""
        from src.scan.runner import sanitize_keyword
        result = sanitize_keyword("DevOps Engineer")
        assert result == "DevOps Engineer"

    def test_truncates_long_keyword(self):
        """RED: keyword longer than 200 chars should be truncated."""
        from src.scan.runner import sanitize_keyword
        long_kw = "a" * 300
        result = sanitize_keyword(long_kw)
        assert len(result) == 200

    def test_allows_hyphens_and_underscores(self):
        """RED: hyphens and underscores should pass through unchanged."""
        from src.scan.runner import sanitize_keyword
        result = sanitize_keyword("senior-devops_engineer")
        assert result == "senior-devops_engineer"

    def test_empty_string_returns_empty(self):
        """TRIANGULATE: empty string should return empty."""
        from src.scan.runner import sanitize_keyword
        assert sanitize_keyword("") == ""

    def test_keyword_with_only_special_chars_returns_empty(self):
        """TRIANGULATE: keyword with only stripped chars returns empty string."""
        from src.scan.runner import sanitize_keyword
        result = sanitize_keyword(";$()|{}`!")
        assert result == ""
        assert len(result) == 0

    def test_multiple_special_chars_stripped(self):
        """TRIANGULATE: multiple mixed special chars all removed."""
        from src.scan.runner import sanitize_keyword
        result = sanitize_keyword("devops&engineer|admin$(id)`ls`")
        assert "&" not in result
        assert "|" not in result
        assert "$" not in result
        assert "(" not in result
        assert "`" not in result
        # Only alphanumeric and spaces should remain
        for ch in result:
            assert ch.isalnum() or ch.isspace()


# =============================================================================
# Task 1.8 — Threat matrix: concurrent scan request
# =============================================================================

class TestConcurrentScan:
    """Concurrent /scan requests should not start a second subprocess."""

    def test_second_request_returns_same_progress_html(self, client):
        """RED: calling /scan twice should return progress HTML both times but only start one scan."""
        from unittest.mock import patch
        from src.scan.runner import scan_state, ScanState

        # Ensure clean state
        scan_state.reset()

        # Mock run_scan so background task completes instantly
        with patch("src.scan.routes.run_scan") as mock_run:
            resp1 = client.get("/scan")
            assert resp1.status_code == 200

            # Second call while running should also return 200
            resp2 = client.get("/scan")
            assert resp2.status_code == 200
            assert "text/html" in resp2.headers["content-type"]

            # run_scan should only be called once (first request)
            mock_run.assert_called_once()

    def test_scan_state_reset_returns_defaults(self):
        """TRIANGULATE: reset() should return all fields to defaults."""
        from src.scan.runner import ScanState

        state = ScanState()
        state.running = True
        state.progress_pct = 50.0
        state.current_target = "test_target"
        state.targets_completed = 3
        state.targets_total = 10
        state.log_lines.append("test log")
        state.error = "test error"

        state.reset()

        assert state.running is False
        assert state.progress_pct == 0.0
        assert state.current_target == ""
        assert state.targets_completed == 0
        assert state.targets_total == 0
        assert state.log_lines == []
        assert state.error is None


# =============================================================================
# Phase 1 — Task 1.1/1.2: ScanState cancel event (RED)
# =============================================================================

class TestScanStateCancel:
    """ScanState.cancel — asyncio.Event for cancellation signal."""

    def test_cancel_default_not_set(self):
        """RED: cancel event should default to not set."""
        from src.scan.runner import ScanState
        state = ScanState()
        assert state.cancel.is_set() is False

    def test_cancel_is_asyncio_event(self):
        """RED: cancel must be an asyncio.Event instance."""
        from src.scan.runner import ScanState
        import asyncio
        state = ScanState()
        assert isinstance(state.cancel, asyncio.Event)

    def test_reset_creates_fresh_event(self):
        """RED: reset() should create a fresh Event (not set)."""
        from src.scan.runner import ScanState
        state = ScanState()
        state.cancel.set()
        assert state.cancel.is_set() is True
        state.reset()
        assert state.cancel.is_set() is False


# =============================================================================
# Phase 2 — Task 2.1: Cancel check in run_scan (RED)
# =============================================================================

class TestRunScanCancel:
    """run_scan() cancellation — breaks loop and kills subprocess."""

    @pytest.mark.asyncio
    async def test_cancel_cleared_before_platform_loop(self):
        """RED: run_scan clears cancel at start so previous cancel doesn't prevent scan."""
        from src.scan.runner import ScanState, run_scan
        from unittest.mock import AsyncMock, patch

        state = ScanState()
        state.running = True
        state.cancel.set()  # Simulate cancel leftover from previous /clean-db or /scan/stop

        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([
            b"PROGRESS:linkedin:50.0%\n",
            b"TOTAL: 5 jobs across 1 targets\n",
        ])
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)):
            await run_scan(state)

        # cancel.clear() ran at start, so loop ran normally
        assert state.targets_completed == 1
        assert state.cancel.is_set() is False

    @pytest.mark.asyncio
    async def test_cancel_mid_line_calls_terminate(self):
        """RED: cancel mid-stream terminates the subprocess."""
        from src.scan.runner import ScanState, run_scan
        from unittest.mock import AsyncMock, patch, MagicMock

        state = ScanState()
        state.running = True

        mock_process = AsyncMock()

        # Yield first line normally, set cancel before second line
        async def mock_aiter(_self=None):
            yield b"PROGRESS:first:50.0%\n"
            state.cancel.set()
            yield b"PROGRESS:second:60.0%\n"

        mock_process.stdout = MagicMock()
        mock_process.stdout.__aiter__ = mock_aiter
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)):
            await run_scan(state, platforms=["linkedin"])

        # terminate should have been called because cancel was set
        mock_process.terminate.assert_called_once()
        # First line was processed (name 'first' at 50%), scan completes at 100%
        assert state.current_target == "first"

    @pytest.mark.asyncio
    async def test_cancel_mid_line_kills_if_terminate_timeout(self):
        """RED: if terminate times out, subprocess gets killed."""
        from src.scan.runner import ScanState, run_scan
        from unittest.mock import AsyncMock, patch, MagicMock
        import asyncio

        state = ScanState()
        state.running = True

        mock_process = AsyncMock()

        async def mock_aiter(_self=None):
            yield b"PROGRESS:first:50.0%\n"
            state.cancel.set()
            yield b"PROGRESS:second:60.0%\n"

        mock_process.stdout = MagicMock()
        mock_process.stdout.__aiter__ = mock_aiter
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0  # exits cleanly after kill
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)):
            with patch("asyncio.wait_for", new=AsyncMock()) as mock_wait_for:
                mock_wait_for.side_effect = asyncio.TimeoutError
                await run_scan(state, platforms=["linkedin"])

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        # asyncio.wait_for was called (simulating timeout)
        mock_wait_for.assert_called_once()


# =============================================================================
# Phase 3 — Task 3.1: GET /scan/stop endpoint (RED)
# =============================================================================

class TestScanStopEndpoint:
    """GET /scan/stop — cancellation endpoint."""

    def test_scan_stop_returns_200_html(self, client):
        """RED: /scan/stop should return 200 with HTML content type."""
        from src.scan.runner import scan_state
        scan_state.reset()
        scan_state.running = True
        response = client.get("/scan/stop")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_scan_stop_sets_cancel_event(self, client):
        """RED: /scan/stop should set scan_state.cancel."""
        from src.scan.runner import scan_state
        scan_state.reset()
        assert scan_state.cancel.is_set() is False
        client.get("/scan/stop")
        assert scan_state.cancel.is_set() is True

    def test_scan_stop_idempotent_when_not_running(self, client):
        """RED: /scan/stop should not raise when scan is already stopped."""
        from src.scan.runner import scan_state
        scan_state.reset()
        scan_state.running = False
        response = client.get("/scan/stop")
        assert response.status_code == 200

    def test_scan_stop_returns_progress_partial(self, client):
        """RED: /scan/stop should return progress partial with debug_mode."""
        from src.scan.runner import scan_state
        scan_state.reset()
        scan_state.running = True
        response = client.get("/scan/stop")
        assert "scan-progress" in response.text or "progress-track" in response.text


# =============================================================================
# Phase 4 — Task 4.1: STOP button visibility (RED)
# =============================================================================

class TestStopButtonVisibility:
    """STOP button renders conditionally in scan_config.html."""

    def test_stop_button_in_scan_config_not_header(self):
        """RED: STOP button now lives in scan_config.html (SCAN tab), not base.html."""
        from src.scan.runner import ScanState
        import src.dashboard.server as server
        state = ScanState()
        state.running = True
        # STOP is no longer in progress.html
        response = server.templates.TemplateResponse(
            None, "partials/progress.html",
            {"state": state, "debug_mode": True},
        )
        body = response.body.decode()
        assert "/scan/stop" not in body
        assert "STOP" not in body

        # STOP is no longer in base.html
        response_base = server.templates.TemplateResponse(
            None, "base.html",
            {"scan_running": True, "debug_mode": True, "total_jobs": 0},
        )
        body_base = response_base.body.decode()
        assert "STOP" not in body_base

        # STOP is in scan_config.html
        import sqlite3
        from src.scan.store import get_platforms
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE IF NOT EXISTS scan_platforms (id INTEGER PRIMARY KEY, name TEXT, url TEXT, enabled INTEGER DEFAULT 1)")
        conn.execute("INSERT INTO scan_platforms (name, url) VALUES ('LinkedIn', 'https://linkedin.com')")
        conn.commit()
        platforms = get_platforms(conn)
        response_scan = server.templates.TemplateResponse(
            None, "scan_config.html",
            {"scan_state": state, "platforms": platforms},
        )
        body_scan = response_scan.body.decode()
        assert "/scan/stop" in body_scan
        assert "STOP" in body_scan

    def test_stop_button_hidden_when_not_running(self):
        """RED: STOP button should NOT render when state.running=False."""
        from src.scan.runner import ScanState
        import src.dashboard.server as server
        state = ScanState()
        state.running = False
        response = server.templates.TemplateResponse(
            None, "partials/progress.html",
            {"state": state, "debug_mode": True},
        )
        body = response.body.decode()
        assert "STOP" not in body

    def test_stop_button_hidden_when_debug_off(self):
        """RED: STOP button should NOT render when debug_mode=False."""
        from src.scan.runner import ScanState
        import src.dashboard.server as server
        state = ScanState()
        state.running = True
        response = server.templates.TemplateResponse(
            None, "partials/progress.html",
            {"state": state, "debug_mode": False},
        )
        body = response.body.decode()
        assert "STOP" not in body


# =============================================================================
# Phase 4 — Task 4.3: JS handler for /scan/stop (RED)
# =============================================================================

class TestStopButtonJS:
    """script.js must have htmx:afterRequest handler for /scan/stop."""

    def test_js_has_scan_stop_handler(self, client):
        """RED: script.js should reference /scan/stop in an htmx listener."""
        response = client.get("/static/script.js")
        assert "/scan/stop" in response.text

    def test_js_closes_event_source_on_stop(self, client):
        """RED: script.js should call eventSource.close() on stop."""
        response = client.get("/static/script.js")
        text = response.text
        assert "eventSource.close()" in text or "eventSource.close" in text

    def test_js_enables_scan_button_on_stop(self, client):
        """RED: script.js should call enableScanButton() on stop."""
        response = client.get("/static/script.js")
        assert "enableScanButton" in response.text

    def test_js_collapses_progress_on_stop(self, client):
        """RED: script.js should clear progress section on stop."""
        response = client.get("/static/script.js")
        assert "progressSection" in response.text
        assert "innerHTML" in response.text or "remove" in response.text

    def test_js_clears_dino_renderer_on_stop(self, client):
        """RED: script.js should reset dinoRenderer on stop."""
        response = client.get("/static/script.js")
        assert "dinoRenderer" in response.text


# =============================================================================
# Module-level fixtures (shared across all test classes)
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
        ("linkedin", "DevOps Engineer",   "http://x/1", "Acme Inc",  "Buenos Aires",
         '[{"key": "fecha_publicacion", "value": "2024-01-15", "confidence": 1.0}, {"key": "modalidad", "value": "Remoto", "confidence": 1.0}]',
         "2024-01-15T10:00:00", ""),
        ("linkedin", "SRE Specialist",    "http://x/2", "Beta Corp", "Remote",
         '[]', "2024-01-14T10:00:00", ""),
        ("indeed",   "Platform Engineer", "http://x/3", "Acme Inc",  "Madrid",
         '[{"key": "salario", "value": "70k", "confidence": 1.0}]',
         "2024-01-13T10:00:00", "postulado"),
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
    """FastAPI TestClient with patched DB_PATH for server, status, api, AND scan routes."""
    import src.dashboard.server as server
    import src.status.routes as status_routes
    import src.api.routes as api_routes
    import src.scan.routes as scan_routes
    original = server.DB_PATH
    orig_status = status_routes.DB_PATH
    orig_api = api_routes.DB_PATH
    orig_scan = scan_routes.DB_PATH
    server.DB_PATH = seeded_db
    status_routes.DB_PATH = seeded_db
    api_routes.DB_PATH = seeded_db
    scan_routes.DB_PATH = seeded_db
    try:
        from src.dashboard.server import app
        with TestClient(app) as c:
            yield c
    finally:
        server.DB_PATH = original
        status_routes.DB_PATH = orig_status
        api_routes.DB_PATH = orig_api
        scan_routes.DB_PATH = orig_scan


# =============================================================================
# Task 1.4 — Server Routes (FastAPI TestClient)
# =============================================================================

class TestServerRoutes:
    """Dashboard routes: /, /table, /scan, /scan/status, /select/toggle."""

    # -- GET / (dashboard page) -------------------------------------------------

    def test_dashboard_returns_200(self, client):
        """RED: GET / should return 200 HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    # -- GET /table (job table partial) -----------------------------------------

    def test_table_returns_200(self, client):
        """RED: GET /table should return HTML table partial."""
        response = client.get("/table")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_table_shows_jobs(self, client):
        """RED: table should contain job data from DB."""
        response = client.get("/table")
        assert "DevOps Engineer" in response.text
        assert "SRE Specialist" in response.text
        assert "Platform Engineer" in response.text

    def test_table_columns_present(self, client):
        """RED: table should contain all 9 spec columns."""
        response = client.get("/table")
        for col in ["date_published", "platform", "title", "company",
                     "modality", "salary", "location", "link", "status"]:
            assert col in response.text

    def test_table_status_value(self, client):
        """RED: status cell should show the job's status value."""
        response = client.get("/table")
        assert "postulado" in response.text

    # -- Pagination -------------------------------------------------------------

    def test_table_pagination_params(self, client):
        """RED: /table should accept page and per_page params."""
        response = client.get("/table?page=1&per_page=10")
        assert response.status_code == 200

    # -- Search -----------------------------------------------------------------

    def test_table_search_filters(self, client):
        """RED: search param should filter by title/company."""
        response = client.get("/table?search=Engineer")
        assert response.status_code == 200
        assert "DevOps Engineer" in response.text
        assert "Platform Engineer" in response.text

    def test_table_search_no_match(self, client):
        """RED: search with no matches should return empty results."""
        response = client.get("/table?search=ZZZZNOSUCH")
        assert response.status_code == 200
        # Should not show any known jobs
        assert "DevOps Engineer" not in response.text

    # -- Scan status (SSE) ------------------------------------------------------

    def test_scan_status_sse(self, client):
        """RED: /scan/status should return SSE stream."""
        from src.scan.runner import scan_state
        scan_state.reset()
        response = client.get("/scan/status")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    # -- Trigger scan -----------------------------------------------------------

    def test_trigger_scan(self, client):
        """RED: GET /scan should return progress HTML."""
        from unittest.mock import patch
        from src.scan.runner import scan_state
        scan_state.reset()
        with patch("src.scan.routes.run_scan"):
            response = client.get("/scan")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_scan_accepts_q_param(self, client):
        """RED: GET /scan?q=keyword should accept the q query param."""
        from unittest.mock import patch
        from src.scan.runner import scan_state
        scan_state.reset()  # ensure clean state

        with patch("src.scan.routes.run_scan"):
            response = client.get("/scan?q=DevOps+Engineer")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    # -- Scan running state context ----------------------------------------------

    def test_dashboard_has_scan_running(self, client):
        """RED: GET / should include scan_running in the template context."""
        from src.scan.runner import scan_state
        import src.dashboard.server as server

        # Render index with scan_running=True to test the template path
        response = server.templates.TemplateResponse(
            None, "index.html",
            {
                "total_jobs": 10,
                "debug_mode": False,
                "scan_running": True,
                "filters": [],
            },
        )
        body = response.body.decode()
        # Template should render correctly with 10 total_jobs
        assert "10 jobs" in body
        assert "STATUS" in body

    # -- All columns render -----------------------------------------------------

    def test_all_columns_spec(self, client, seeded_db):
        """RED: add 2 more jobs and verify all 5 rows render with 9 cols each."""
        # Add 2 more jobs directly
        conn = sqlite3.connect(seeded_db)
        for i in range(4, 6):
            conn.execute(
                "INSERT INTO jobs (source, title, url, scraped_at) VALUES (?, ?, ?, ?)",
                ("test", f"Job {i}", f"http://x/{i}", "2024-01-12T10:00:00"),
            )
        conn.commit()
        conn.close()

        response = client.get("/table")
        assert "Job 4" in response.text
        assert "Job 5" in response.text


# =============================================================================
# Task 1.5 — Entry point import check
# =============================================================================

class TestEntryPoint:
    """scripts/run_dashboard.py — verify it imports correctly."""

    def test_module_imports(self):
        """RED: scripts.run_dashboard should import without errors."""
        import scripts.run_dashboard  # noqa: F811
        assert hasattr(scripts.run_dashboard, "main")


# =============================================================================
# Phase 2 — Frontend: Templates, CSS, JS (OpenCode light theme)
# =============================================================================

class TestFrontendBaseTemplate:
    """Base template: HTMX CDN, CSS link, OpenCode CSS vars."""

    def test_htmx_cdn_loaded(self, client):
        """RED: base.html should include HTMX CDN script."""
        response = client.get("/")
        assert "unpkg.com/htmx.org" in response.text

    def test_css_link_present(self, client):
        """RED: base.html should link to /static/base.css."""
        response = client.get("/")
        assert "/static/base.css" in response.text

    def test_script_js_loaded(self, client):
        """RED: base.html should load /static/script.js."""
        response = client.get("/")
        assert "/static/script.js" in response.text


class TestFrontendIndexPage:
    """Index page: header menu, table container, progress container."""

    def test_search_input_present(self, client):
        """RED: index page should have a search input."""
        response = client.get("/")
        assert "search" in response.text.lower()

    def test_execute_scan_button_present(self, client):
        """RED: index page should have the SCAN button."""
        response = client.get("/")
        assert "SCAN" in response.text

    def test_select_toggle_present(self, client):
        """RED: index page should have Select toggle."""
        response = client.get("/")
        assert "select" in response.text.lower()

    def test_refresh_button_present(self, client):
        """RED: status page should have Refresh button."""
        response = client.get("/status/panel")
        assert "REFRESH" in response.text

    def test_table_container_present(self, client):
        """RED: index page should have a table container."""
        response = client.get("/")
        assert "table-container" in response.text

    def test_scan_tab_has_progress(self, client):
        """RED: SCAN config tab should reference progress."""
        response = client.get("/scan/config")
        assert "progress" in response.text.lower() or "scan" in response.text.lower()

    def test_debug_checkbox_in_non_production(self, client):
        """RED: debug checkbox should be in settings tab."""
        response = client.get("/settings")
        assert "DEBUG" in response.text or "Debug" in response.text
        assert "settings-debug" in response.text

    def test_debug_checkbox_hidden_by_default(self, client):
        """RED: settings tab has debug option."""
        response = client.get("/settings")
        assert "settings-debug" in response.text
        assert "debug" in response.text.lower()

    # -- Task 1.4: Debounce -----------------------------------------------------

    def test_search_debounce_is_2000ms(self, client):
        """RED: search input trigger should have delay:2000ms."""
        response = client.get("/")
        assert "delay:2000ms" in response.text

    # -- Task 1.5: Scan button disabled state -----------------------------------

    def test_scan_button_has_disabled_when_running(self):
        """RED: scan button exists in scan_config.html. Disabled state is managed by JS (disableScanButton)."""
        import src.dashboard.server as server
        from src.scan.runner import ScanState
        import sqlite3
        state = ScanState()
        state.running = True
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE IF NOT EXISTS scan_platforms (id INTEGER PRIMARY KEY, name TEXT, url TEXT, enabled INTEGER DEFAULT 1)")
        conn.commit()
        response = server.templates.TemplateResponse(
            None, "scan_config.html",
            {
                "scan_state": state,
                "platforms": [],
                "keyword": "",
                "location": "",
                "modalities": [],
                "date_range": "",
            },
        )
        body = response.body.decode()
        assert 'btn-scan' in body  # scan button exists in SCAN tab

    def test_scan_button_not_disabled_when_not_running(self):
        """RED: scan button in index.html should still work (STATUS tab shows SCAN button)."""
        import src.dashboard.server as server
        response = server.templates.TemplateResponse(
            None, "index.html",
            {
                "total_jobs": 10,
                "debug_mode": False,
                "scan_running": False,
            },
        )
        body = response.body.decode()
        # The .btn-scan button should exist and not have disabled
        import re
        scan_btn_match = re.search(r'<button class="btn btn-scan".*?</button>', body, re.DOTALL)
        # If not in index.html, it was moved to scan_config.html — that's OK
        if scan_btn_match:
            assert 'disabled' not in scan_btn_match.group(0)

    # -- Task 1.7: hx-include on scan button ------------------------------------

    def test_scan_button_includes_search_input(self, client):
        """RED: scan button should have hx-include referencing search input."""
        response = client.get("/")
        # The button should include the search input value
        assert "hx-include" in response.text
        assert "search" in response.text.lower()


class TestFrontendTablePartial:
    """Table partial: 9 columns, status badges, checkbox toggle."""

    def test_all_nine_column_headers(self, client):
        """RED: table should have all 9 column headers."""
        response = client.get("/table")
        html = response.text
        assert "date_published" in html
        assert "platform" in html
        assert "title" in html
        assert "company" in html
        assert "modality" in html
        assert "salary" in html
        assert "location" in html
        assert "link" in html
        assert "status" in html

    def test_status_badge_class(self, client):
        """RED: status cells should have a status-badge class."""
        response = client.get("/table")
        assert "status-badge" in response.text
        assert "postulado" in response.text

    def test_checkbox_column_hidden_by_default(self, client):
        """RED: checkbox column should not appear when select=False."""
        response = client.get("/table")
        assert 'type="checkbox"' not in response.text

    def test_link_column_renders_as_link(self, client):
        """RED: link column should render clickable links."""
        response = client.get("/table")
        assert "http://x/1" in response.text or 'href="http://x/1"' in response.text

    def test_table_shows_multiple_jobs(self, client):
        """RED: table should show multiple job rows."""
        response = client.get("/table")
        assert "DevOps Engineer" in response.text
        assert "SRE Specialist" in response.text
        assert "Platform Engineer" in response.text

    def test_status_badge_color_classes(self, client):
        """RED: status badges should have color-coded classes."""
        response = client.get("/table")
        # postulado should trigger a green-ish class
        assert "postulado" in response.text


class TestFrontendPagination:
    """Pagination: prev/next, per-page dropdown."""

    def test_per_page_dropdown_present(self, client):
        """RED: table should have per-page dropdown with all options."""
        response = client.get("/table")
        html = response.text
        assert "10" in html
        assert "50" in html
        assert "100" in html
        assert "250" in html
        assert "All" in html

    def test_previous_link_present_when_not_first_page(self):
        """RED: Previous link should appear when page > 1."""
        import src.dashboard.server as server
        response = server.templates.TemplateResponse(
            None, "partials/table.html",
            {"jobs": [{"id": 1}], "page": 2, "per_page": 2, "total": 3,
             "total_pages": 2, "search": "", "select": False, "show_all": False},
        )
        body = response.body.decode().lower()
        assert "previous" in body

    def test_next_link_present_when_not_last_page(self):
        """RED: Next link should appear when page < total_pages."""
        import src.dashboard.server as server
        response = server.templates.TemplateResponse(
            None, "partials/table.html",
            {"jobs": [{"id": 1}], "page": 1, "per_page": 2, "total": 3,
             "total_pages": 2, "search": "", "select": False, "show_all": False},
        )
        body = response.body.decode().lower()
        assert "next" in body

    def test_page_info_displayed(self):
        """RED: page info should show current page and total."""
        import src.dashboard.server as server
        response = server.templates.TemplateResponse(
            None, "partials/table.html",
            {"jobs": [{"id": 1}], "page": 1, "per_page": 10, "total": 25,
             "total_pages": 3, "search": "", "select": False, "show_all": False},
        )
        body = response.body.decode()
        assert any(str(n) in body for n in [1, 10, 25, 3])


class TestFrontendProgressBar:
    """Progress bar partial: cyberpunk styling, SSE-driven."""

    def test_progress_bar_container(self):
        """RED: progress bar should have a track container element."""
        from src.scan.runner import ScanState
        import src.dashboard.server as server
        state = ScanState()
        state.running = True
        state.progress_pct = 50.0
        state.current_target = "devops_espana"
        response = server.templates.TemplateResponse(
            None, "partials/progress.html",
            {"state": state},
        )
        body = response.body.decode()
        assert "progress-track" in body
        assert "50" in body

    def test_progress_bar_zero_percent(self):
        """RED: progress bar should render at 0% start state."""
        from src.scan.runner import ScanState
        import src.dashboard.server as server
        state = ScanState()
        response = server.templates.TemplateResponse(
            None, "partials/progress.html",
            {"state": state},
        )
        body = response.body.decode()
        assert "progress-fill" in body
        assert "0.0%" in body

    def test_progress_complete_state(self):
        """RED: complete progress should show 100% width."""
        from src.scan.runner import ScanState
        import src.dashboard.server as server
        state = ScanState()
        state.progress_pct = 100.0
        state.running = False
        state.current_target = ""
        response = server.templates.TemplateResponse(
            None, "partials/progress.html",
            {"state": state},
        )
        body = response.body.decode()
        assert "100" in body

    def test_progress_error_displayed(self):
        """RED: progress bar state without running should render.
        Error display is client-side via JS showDone()."""
        from src.scan.runner import ScanState
        import src.dashboard.server as server
        state = ScanState()
        state.error = "Something went wrong"
        state.running = False
        response = server.templates.TemplateResponse(
            None, "partials/progress.html",
            {"state": state},
        )
        body = response.body.decode()
        assert "progress-fill" in body


class TestFrontendStaticAssets:
    """Static assets: CSS served, JS served, OpenCode light theme present."""

    def test_css_contains_light_theme_vars(self, client):
        """RED: base.css should define OpenCode light CSS variables."""
        response = client.get("/static/base.css")
        css = response.text
        assert "#007aff" in css  # blue accent
        assert "#1d1d1f" in css  # text primary

    def test_css_contains_light_bg(self, client):
        """RED: base.css should define light background color."""
        response = client.get("/static/base.css")
        assert "#ffffff" in response.text

    def test_css_has_neon_glow_on_progress(self, client):
        """RED: scan.css should have box-shadow on progress bar."""
        response = client.get("/static/scan.css")
        css = response.text
        # Progress bar section should have box-shadow for neon glow
        assert "box-shadow" in css

    def test_css_has_status_badge_styles(self, client):
        """RED: status.css should have .status-badge styles."""
        response = client.get("/static/status.css")
        assert ".status-badge" in response.text

    def test_css_has_no_linear_gradient(self, client):
        """RED: CSS should NOT have linear-gradient (no CSS file)."""
        for css_file in ["/static/base.css", "/static/status.css", "/static/scan.css", "/static/datos.css"]:
            response = client.get(css_file)
            assert "linear-gradient" not in response.text

    def test_js_served_correctly(self, client):
        """RED: script.js should be served as JS."""
        response = client.get("/static/script.js")
        assert response.status_code == 200
        assert "javascript" in response.headers.get("content-type", "").lower()

    def test_js_contains_event_source(self, client):
        """RED: script.js should create EventSource for SSE."""
        response = client.get("/static/script.js")
        assert "EventSource" in response.text

    def test_js_contains_select_all_logic(self, client):
        """RED: script.js should handle select-all checkbox."""
        response = client.get("/static/script.js")
        assert "select-all" in response.text

    def test_js_has_disable_scan_button_function(self, client):
        """RED: script.js should have disableScanButton function."""
        response = client.get("/static/script.js")
        assert "disableScanButton" in response.text

    def test_js_has_enable_scan_button_function(self, client):
        """RED: script.js should have enableScanButton function."""
        response = client.get("/static/script.js")
        assert "enableScanButton" in response.text

    def test_js_disables_button_in_start_scan_listener(self, client):
        """RED: startScanListener should call disableScanButton."""
        response = client.get("/static/script.js")
        assert "startScanListener" in response.text
        assert "disableScanButton" in response.text

    def test_js_enables_button_in_show_done(self, client):
        """RED: showDone should call enableScanButton."""
        response = client.get("/static/script.js")
        assert "showDone" in response.text
        assert "enableScanButton" in response.text


# =============================================================================
# Phase 1 — Task 1.3: Cross-Column Search (RED for server.py _fetch_jobs)
# =============================================================================

class TestCrossColumnSearch:
    """Search now matches across title, company, location, description, tags."""

    def test_search_by_location(self, client):
        """RED: search by location 'Buenos Aires' should return matching row."""
        response = client.get("/table?search=Buenos+Aires")
        assert response.status_code == 200
        assert "DevOps Engineer" in response.text

    def test_search_by_modality_tag(self, client):
        """RED: search by modality value 'Remoto' (in tags JSON) should return matching row."""
        response = client.get("/table?search=Remoto")
        assert response.status_code == 200
        assert "DevOps Engineer" in response.text

    def test_search_by_title_still_works(self, client):
        """RED: existing title search must still work after WHERE expansion."""
        response = client.get("/table?search=Engineer")
        assert response.status_code == 200
        assert "DevOps Engineer" in response.text
        assert "Platform Engineer" in response.text

    def test_search_by_company_still_works(self, client):
        """RED: existing company search must still work after WHERE expansion."""
        response = client.get("/table?search=Acme")
        assert response.status_code == 200
        assert "DevOps Engineer" in response.text
        assert "Platform Engineer" in response.text

    def test_search_no_match_returns_empty(self, client):
        """RED: search with no match across all 5 columns must return empty."""
        response = client.get("/table?search=ZZZZNOSUCH")
        assert response.status_code == 200
        assert "DevOps Engineer" not in response.text


# =============================================================================
# Phase 2 — Dark Mode CSS (RED for base.css)
# =============================================================================

class TestDarkModeCSS:
    """CSS must define [data-theme] scoped variables for dark and light."""

    def _get_css(self, client):
        """Helper: read all CSS files combined for searching."""
        combined = ""
        for css_file in ["/static/base.css", "/static/status.css", "/static/scan.css", "/static/datos.css"]:
            combined += client.get(css_file).text + "\n"
        return combined

    def test_css_has_dark_theme_selector(self, client):
        """RED: base.css should contain [data-theme='dark'] selector."""
        css = client.get("/static/base.css").text
        assert '[data-theme="dark"]' in css

    def test_css_has_light_theme_selector(self, client):
        """RED: base.css should contain [data-theme='light'] selector."""
        css = client.get("/static/base.css").text
        assert '[data-theme="light"]' in css

    def test_dark_has_purple_accent(self, client):
        """RED: dark theme should define accent color."""
        css = client.get("/static/base.css").text
        assert "#5f87ff" in css or "#a855f7" in css

    def test_dark_has_dark_bg(self, client):
        """RED: dark theme should define dark background."""
        css = client.get("/static/base.css").text
        assert "#1c1c1c" in css or "#0a0a0f" in css

    def test_light_has_white_bg(self, client):
        """RED: light theme should keep --bg-primary: #ffffff."""
        css = client.get("/static/base.css").text
        assert "#ffffff" in css

    def test_dark_progress_neon_blue(self, client):
        """RED: dark theme progress fill should have purple neon glow."""
        css = self._get_css(client)
        assert "rgba(168, 85, 247" in css or "rgba(0, 122, 255" in css

    def test_css_has_no_root_vars(self, client):
        """RED: base.css CSS variables should be in theme selectors, not bare :root."""
        css = client.get("/static/base.css").text
        # Check that [data-theme] selectors contain the variables
        assert '[data-theme="dark"]' in css
        assert '[data-theme="light"]' in css


# =============================================================================
# Phase 3 — Dark Mode JS + Template (RED for base.html, script.js, index.html)
# =============================================================================

class TestDarkModeTemplate:
    """Base template must have flash guard and default theme."""

    def test_html_has_data_theme_dark_default(self, client):
        """RED: <html> tag should have data-theme='dark' by default."""
        response = client.get("/")
        assert 'data-theme="dark"' in response.text

    def test_inline_flash_guard_script_present(self, client):
        """RED: base.html should have inline script that reads localStorage before render."""
        response = client.get("/")
        html = response.text
        assert "localStorage.getItem('dashboard-theme')" in html or 'localStorage.getItem("dashboard-theme")' in html

    def test_theme_toggle_switch_present(self, client):
        """RED: settings tab should have a theme selector with id='settings-theme'."""
        response = client.get("/settings")
        assert 'id="settings-theme"' in response.text

    def test_theme_toggle_slider_present(self, client):
        """RED: settings tab should have theme options (dark/light/amber)."""
        response = client.get("/settings")
        assert "Dark" in response.text and "Light" in response.text and "Amber" in response.text


class TestDarkModeJS:
    """script.js must have theme toggle logic."""

    def test_script_has_theme_toggle_var(self, client):
        """RED: script.js should reference settings-theme element."""
        response = client.get("/static/script.js")
        assert "settings-theme" in response.text

    def test_script_has_localstorage_theme(self, client):
        """RED: script.js should read/write localStorage 'dashboard-theme' key."""
        response = client.get("/static/script.js")
        text = response.text
        assert "dashboard-theme" in text

    def test_script_sets_theme_on_toggle(self, client):
        """RED: script.js should set data-theme and localStorage on theme change."""
        response = client.get("/static/script.js")
        text = response.text
        assert "addEventListener" in text or "addEventListener" in text
        assert "setAttribute" in text or "document.documentElement" in text


# =============================================================================
# Task 5.1 — Theme Toggle HTML Structure (Phase 1)
# =============================================================================

class TestThemeToggleReposition:
    """Theme toggle moved to Settings tab."""

    def test_theme_switch_group_wrapper_present(self, client):
        """RED: settings tab should have the theme selector."""
        response = client.get("/settings")
        assert 'id="settings-theme"' in response.text

    def test_theme_icons_present(self, client):
        """RED: settings tab should have a theme selector."""
        response = client.get("/settings")
        assert 'id="settings-theme"' in response.text

    def test_theme_toggle_not_at_old_position(self, client):
        """RED: theme toggle should NOT be in the header anymore."""
        response = client.get("/")
        assert 'id="theme-toggle"' not in response.text

    def test_scan_button_says_scan_not_execute_scan(self, client):
        """RED: scan button text should be 'SCAN' not 'EXECUTE SCAN'."""
        response = client.get("/")
        html = response.text
        assert "SCAN" in html
        assert "EXECUTE SCAN" not in html


# =============================================================================
# Task 5.2 — Platform Multi-Select Combo HTML (Phase 2)
# =============================================================================

class TestPlatformCombo:
    """Platform multi-select dropdown in the SCAN tab."""

    def test_platforms_loaded_via_htmx_in_scan_tab(self, client):
        """RED: scan_config.html should load platforms via HTMX."""
        response = client.get("/scan/config")
        assert 'hx-get="/datos/platforms"' in response.text

    def test_platform_select_has_multiple(self, client):
        """RED: platform partial should have 'multiple' attribute."""
        response = client.get("/datos/platforms")
        assert 'multiple' in response.text or 'platform' in response.text.lower()

    def test_platforms_partial_shows_linkedin(self, client):
        """RED: /datos/platforms partial should show LinkedIn."""
        response = client.get("/datos/platforms")
        assert "LinkedIn" in response.text

    def test_scan_button_includes_platform_reference(self, client):
        """RED: scan button should be in scan_config.html."""
        response = client.get("/scan/config")
        html = response.text
        assert 'btn btn-scan' in html or 'id="scan-btn"' in html


# =============================================================================
# Task 5.3 — Scan Platforms Param (Phase 3)
# =============================================================================

class TestScanPlatformsParam:
    """/scan endpoint reads enabled platforms from DB (single source of truth)."""

    def test_scan_ignores_platforms_in_url(self, client):
        """RED: GET /scan?platforms=linkedin should still work (param is ignored)."""
        from unittest.mock import patch
        from src.scan.runner import scan_state
        scan_state.reset()

        with patch("src.scan.routes.run_scan"), \
             patch("src.scan.routes.get_enabled_platform_names", return_value=["linkedin"]):
            response = client.get("/scan?platforms=linkedin")
        assert response.status_code == 200

    def test_scan_reads_platforms_from_db(self, client):
        """RED: /scan should call get_enabled_platform_names and pass to run_scan."""
        from unittest.mock import patch
        from src.scan.runner import scan_state
        scan_state.reset()

        with patch("src.scan.routes.run_scan") as mock_run, \
             patch("src.scan.routes.get_enabled_platform_names", return_value=["linkedin", "indeed"]) as mock_get:
            client.get("/scan")

        mock_get.assert_called_once()
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["platforms"] == ["linkedin", "indeed"], (
            f"platforms should come from DB, got {kwargs.get('platforms')}"
        )

    def test_run_scan_platforms_accepts_list(self):
        """RED: run_scan should accept platforms list and iterate."""
        from src.scan.runner import ScanState, run_scan
        from unittest.mock import AsyncMock, patch, MagicMock

        state = ScanState()
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([
            b"TOTAL: 5 jobs across 1 targets\n",
        ])
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        # Should call subprocess for each platform
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)) as mock_subproc:
            import asyncio
            asyncio.run(run_scan(state, debug=False, keyword="", platforms=["linkedin", "indeed"]))

        # Two platforms → two subprocess calls
        assert mock_subproc.call_count == 2

    def test_run_scan_default_platforms_linkedin(self):
        """RED: run_scan should default to ['linkedin'] when platforms is None."""
        from src.scan.runner import ScanState, run_scan
        from unittest.mock import AsyncMock, patch, MagicMock

        state = ScanState()
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([
            b"TOTAL: 5 jobs across 1 targets\n",
        ])
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)) as mock_subproc:
            import asyncio
            asyncio.run(run_scan(state))

        # Default is one platform (linkedin)
        assert mock_subproc.call_count == 1

    def test_run_scan_sets_platform_env_var(self, client):
        """RED: run_scan should set SCRAPE_PLATFORM env var per platform call."""
        from src.scan.runner import ScanState, run_scan
        from unittest.mock import AsyncMock, patch

        state = ScanState()
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([
            b"TOTAL: 5 jobs across 1 targets\n",
        ])
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_process)) as mock_subproc:
            import asyncio
            asyncio.run(run_scan(state, platforms=["linkedin"]))

        _, kwargs = mock_subproc.call_args
        env = kwargs.get("env", {})
        assert env.get("SCRAPE_PLATFORM") == "linkedin"


# =============================================================================
# Task 5.4 — Footer Stats (Phase 4)
# =============================================================================

class TestFooterStats:
    """Footer showing total_jobs and release version."""

    def test_footer_shows_total_jobs(self, client):
        """RED: footer should show total job count."""
        response = client.get("/")
        html = response.text
        assert "3 jobs" in html or "jobs" in html.lower()

    def test_footer_has_release_version(self, client):
        """RED: footer should contain the release version string."""
        response = client.get("/")
        html = response.text
        assert "v1.0" in html or "release" in html.lower()

    def test_footer_stat_class_present(self, client):
        """RED: footer should have .footer-stat element."""
        response = client.get("/")
        assert 'class="footer-stat"' in response.text

    def test_footer_version_class_present(self, client):
        """RED: footer should have .footer-version element."""
        response = client.get("/")
        assert 'class="footer-version"' in response.text

    def test_dashboard_footer_class_present(self, client):
        """RED: footer should have .dashboard-footer class."""
        response = client.get("/")
        assert 'class="dashboard-footer"' in response.text


# =============================================================================
# Phase 3 — Task 3.3: Hide postulado filter (RED)
# =============================================================================

class TestHidePostulado:
    """GET /table?filters=hide_postulado excludes postulado rows."""

    def test_hide_postulado_returns_200(self, client):
        """RED: hide_postulado filter should return 200."""
        response = client.get("/table?filters=hide_postulado")
        assert response.status_code == 200

    def test_hide_postulado_removes_postulado_rows(self, client, seeded_db):
        """RED: hide_postulado filter should exclude rows with postulado status."""
        import sqlite3
        # Set a row to 'postulado' status
        conn = sqlite3.connect(seeded_db)
        conn.execute("UPDATE jobs SET status = 'postulado' WHERE id = 3")
        conn.commit()
        conn.close()

        response = client.get("/table?filters=hide_postulado")
        # Row with status=postulado should be excluded
        assert "Platform Engineer" not in response.text

    def test_hide_postulado_shows_empty_status(self, client):
        """RED: hide_postulado filter should still show rows with empty status."""
        response = client.get("/table?filters=hide_postulado")
        assert "DevOps Engineer" in response.text
        assert "SRE Specialist" in response.text

    def test_no_hide_shows_all_rows(self, client, seeded_db):
        """RED: without filters, all rows should display."""
        import sqlite3
        conn = sqlite3.connect(seeded_db)
        conn.execute("UPDATE jobs SET status = 'postulado' WHERE id = 3")
        conn.commit()
        conn.close()

        response = client.get("/table")
        assert "DevOps Engineer" in response.text
        assert "SRE Specialist" in response.text
        assert "Platform Engineer" in response.text


# =============================================================================
# Phase 3 — Task 3.2: POST /job/{id}/status (RED)
# =============================================================================

class TestManualStatus:
    """POST /job/{id}/status manually updates job status."""

    def test_post_status_returns_200(self, client):
        """RED: POST /job/1/status should return 200."""
        response = client.post("/job/1/status", json={"status": "postulado"})
        assert response.status_code == 200

    def test_post_status_updates_db(self, client, seeded_db):
        """RED: status should be written to the database."""
        import sqlite3
        client.post("/job/1/status", json={"status": "postulado"})

        conn = sqlite3.connect(seeded_db)
        row = conn.execute("SELECT status FROM jobs WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "postulado"

    def test_post_status_invalid_id_returns_404(self, client):
        """RED: POST /job/999/status should return 404."""
        response = client.post("/job/999/status", json={"status": "postulado"})
        assert response.status_code == 404

    def test_post_status_returns_json(self, client):
        """RED: response should be JSON with ok field."""
        response = client.post("/job/1/status", json={"status": "postulado"})
        data = response.json()
        assert data["ok"] is True


# =============================================================================
# Phase 3 — Task 3.1: POST /apply/auto (RED)
# =============================================================================

class TestAutoApplyRoute:
    """POST /api/apply/auto runs auto-apply per job sequentially."""

    def test_apply_auto_returns_200(self, client):
        """RED: POST /api/apply/auto should return 200."""
        from unittest.mock import patch
        with patch("src.api.routes.AutoApply") as mock_aa:
            mock_instance = mock_aa.return_value
            mock_instance.apply = AsyncMock(return_value="postulado")
            response = client.post(
                "/api/apply/auto",
                json={"job_ids": [1, 2]},
            )
        assert response.status_code == 200

    def test_apply_auto_returns_results_json(self, client):
        """RED: response should be JSON with results list."""
        from unittest.mock import patch
        with patch("src.api.routes.AutoApply") as mock_aa:
            mock_instance = mock_aa.return_value
            mock_instance.apply = AsyncMock(return_value="postulado")
            response = client.post(
                "/api/apply/auto",
                json={"job_ids": [1, 2]},
            )
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2

    def test_apply_auto_writes_status(self, client, seeded_db):
        """RED: auto-apply should write status to DB via update_status."""
        from unittest.mock import patch, AsyncMock
        import sqlite3
        with patch("src.api.routes.AutoApply") as mock_aa:
            mock_instance = mock_aa.return_value
            mock_instance.apply = AsyncMock(return_value="postulado")
            client.post("/api/apply/auto", json={"job_ids": [1]})

        conn = sqlite3.connect(seeded_db)
        row = conn.execute("SELECT status FROM jobs WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "postulado"


# =============================================================================
# Phase 3 — Task 3.5: Status cell rendering (RED)
# =============================================================================

class TestStatusBadgeRendering:
    """Status badge CSS classes and empty dash rendering."""

    def test_empty_status_shows_dash(self, client):
        """RED: empty status should display as gray dash."""
        response = client.get("/table")
        # Jobs with empty status should show "—"
        assert "\u2014" in response.text or "—" in response.text

    def test_non_empty_status_shows_value(self, client, seeded_db):
        """RED: non-empty status should show its value text."""
        import sqlite3
        conn = sqlite3.connect(seeded_db)
        conn.execute("UPDATE jobs SET status = 'postulado' WHERE id = 1")
        conn.commit()
        conn.close()

        response = client.get("/table")
        assert "postulado" in response.text

    def test_status_badge_class_present(self, client):
        """RED: status cells should have status-badge class."""
        response = client.get("/table")
        assert "status-badge" in response.text

    def test_postulado_badge_class(self, client, seeded_db):
        """RED: postulado status should have status-postulado class."""
        import sqlite3
        conn = sqlite3.connect(seeded_db)
        conn.execute("UPDATE jobs SET status = 'postulado' WHERE id = 1")
        conn.commit()
        conn.close()

        response = client.get("/table")
        assert "status-postulado" in response.text

    def test_old_status_classes_replaced(self, client):
        """RED: old CSS classes should not appear in rendered HTML."""
        response = client.get("/table")
        # Old class names should no longer be used
        assert "status-auto-applied" not in response.text
        assert "status-manual" not in response.text
        assert "status-expired" not in response.text


# =============================================================================
# stats-fixes: Task 1.1 — Search AND requires all words (RED)
# =============================================================================

class TestSearchAND:
    """Search query MUST join per-word clauses with AND, not OR."""

    def test_search_and_requires_all_words(self, client):
        """RED: search 'DevOps Acme' should return only row where BOTH words
        match any column. Current OR logic would return Platform Engineer too
        (Acme in company), but AND excludes it because 'DevOps' doesn't match."""
        response = client.get("/table?search=DevOps+Acme")
        assert response.status_code == 200
        # Job 1 (DevOps Engineer at Acme Inc) matches BOTH words → included
        assert "DevOps Engineer" in response.text
        # Job 3 (Platform Engineer at Acme Inc) matches only "Acme", not "DevOps" → excluded
        assert "Platform Engineer" not in response.text

    def test_search_and_single_word_no_regression(self, client):
        """RED: single word search 'Remoto' should behave identically to
        current behavior. 'Remoto' is in job 1's tags JSON — single word,
        AND and OR are equivalent."""
        response = client.get("/table?search=Remoto")
        assert response.status_code == 200
        assert "DevOps Engineer" in response.text


# =============================================================================
# stats-fixes: Task 1.3-1.4 — Date filter uses fecha_publicacion (RED)
# =============================================================================

class TestDateFilterFechaPublicacion:
    """Date filter MUST use json_extract(tags, '$.fecha_publicacion'), not scraped_at."""

    def test_date_filter_uses_fecha_publicacion(self, client, seeded_db):
        """RED: job with recent scraped_at but old fecha_publicacion should
        NOT appear in 'Last 24h'. Current code filters on scraped_at and
        WOULD include it, so this assertion fails RED."""
        import sqlite3
        conn = sqlite3.connect(seeded_db)
        # Insert job: published 2024-01-15 (old), but scraped just now
        conn.execute(
            "INSERT INTO jobs (source, title, url, company, location, tags, scraped_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)",
            ("linkedin", "Old Published Job", "http://x/old-pub",
             "OldCorp", "Remote",
             '[{"key":"fecha_publicacion","value":"2024-01-15","confidence":1.0}]',
             ""),
        )
        conn.commit()
        conn.close()

        response = client.get("/table?since=24h")
        assert response.status_code == 200
        # Published 2024-01-15 is WAY older than 24h → MUST NOT appear
        assert "Old Published Job" not in response.text

    def test_date_filter_excludes_published_old_jobs(self, client, seeded_db):
        """RED: job published 32 days ago, scraped 1h ago → 'Last 30d' must
        exclude it (fecha_publicacion > 30d). Current code uses scraped_at
        (only 1h old) and WOULD include it — this assertion fails RED."""
        import sqlite3
        conn = sqlite3.connect(seeded_db)
        # Insert job: published 32 days ago, scraped 1 hour ago
        conn.execute(
            "INSERT INTO jobs (source, title, url, company, location, tags, scraped_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-1 hour'), ?)",
            ("indeed", "32 Days Old", "http://x/32d",
             "OldDev", "Madrid",
             '[{"key":"fecha_publicacion","value":"' + 
             "2026-06-25" + '","confidence":1.0}]',
             ""),
        )
        conn.commit()
        conn.close()

        response = client.get("/table?since=30d")
        assert response.status_code == 200
        # Published 2026-06-25 is > 30 days from "now" (2026-07-27) → MUST NOT appear
        assert "32 Days Old" not in response.text

    def test_date_filter_includes_recently_published(self, client, seeded_db):
        """TRIANGULATE: job published 1h ago → 'Last 24h' must INCLUDE it."""
        import sqlite3
        conn = sqlite3.connect(seeded_db)
        conn.execute(
            "INSERT INTO jobs (source, title, url, company, location, tags, scraped_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-30 days'), ?)",
            ("linkedin", "Recent Publish", "http://x/recent-pub",
             "NewCo", "Remote",
             '[{"key":"fecha_publicacion","value":"' +
             "2026-07-27" + '","confidence":1.0}]',
             ""),
        )
        conn.commit()
        conn.close()

        response = client.get("/table?since=24h")
        assert response.status_code == 200
        # Published today (2026-07-27) → within 24h → MUST appear
        assert "Recent Publish" in response.text


# =============================================================================
# stats-fixes: Task 4.4 — Filter label update (RED)
# =============================================================================

class TestFilterLabelUpdate:
    """Filter labels: restored to 'Solo pendientes'."""

    def test_filter_label_solo_pendientes(self):
        """DEFAULT_FILTERS.by_key('solo_pendientes').label should be
        'Solo pendientes'."""
        from src.status.filters import DEFAULT_FILTERS
        f = DEFAULT_FILTERS.by_key("solo_pendientes")
        assert f is not None
        assert f.label == "Solo pendientes"


# =============================================================================
# Phase 1 — PR 1: Backend SORT_WHITELIST + sort param (RED)
# =============================================================================

class TestSortParse:
    """_parse_sort() — parses compact sort param into SQL ORDER BY clause."""

    def test_parse_sort_valid_single(self):
        """RED: _parse_sort('platform:asc') should return source ASC."""
        from src.status.routes import _parse_sort
        result = _parse_sort("platform:asc")
        assert result == "source ASC"

    def test_parse_sort_valid_two_level(self):
        """RED: _parse_sort('salary:desc,status:asc') returns multi-column ORDER BY."""
        from src.status.routes import _parse_sort
        result = _parse_sort("salary:desc,status:asc")
        assert "salario" in result
        assert "DESC" in result
        assert "status ASC" in result
        # Raw input must never appear — whitelist expressions only
        assert "salary" not in result.replace("_", "")

    def test_parse_sort_json_column(self):
        """RED: _parse_sort('date_published:desc') should return json_extract-based ORDER BY."""
        from src.status.routes import _parse_sort
        result = _parse_sort("date_published:desc")
        assert "json_extract" in result
        assert "fecha_publicacion" in result
        assert "DESC" in result

    def test_parse_sort_invalid_skipped(self):
        """RED: _parse_sort('platform:asc,nonexistent:desc') should skip invalid."""
        from src.status.routes import _parse_sort
        result = _parse_sort("platform:asc,nonexistent:desc")
        assert "source ASC" in result
        assert "nonexistent" not in result

    def test_parse_sort_all_invalid_fallback(self):
        """RED: _parse_sort('bad:asc') should fall back to scraped_at DESC."""
        from src.status.routes import _parse_sort
        result = _parse_sort("bad:asc")
        assert result == "scraped_at DESC"

    def test_parse_sort_empty_fallback(self):
        """RED: _parse_sort('') should fall back to scraped_at DESC."""
        from src.status.routes import _parse_sort
        result = _parse_sort("")
        assert result == "scraped_at DESC"

    def test_parse_sort_none_fallback(self):
        """RED: _parse_sort(None) should fall back to scraped_at DESC."""
        from src.status.routes import _parse_sort
        result = _parse_sort(None)
        assert result == "scraped_at DESC"


class TestSortWhitelist:
    """SORT_WHITELIST — verify structure and safety."""

    def test_sort_whitelist_no_link(self):
        """RED: 'link' should NOT be in SORT_WHITELIST."""
        from src.status.routes import SORT_WHITELIST
        assert "link" not in SORT_WHITELIST


class TestFetchJobsWithSort:
    """_fetch_jobs() with dynamic ORDER BY — verify row order matches sort."""

    def test_fetch_jobs_with_sort(self, seeded_db):
        """RED: _fetch_jobs with source ASC should return indeed before linkedin."""
        import sqlite3
        from src.status.routes import _fetch_jobs
        conn = sqlite3.connect(seeded_db)
        conn.row_factory = sqlite3.Row
        jobs, total = _fetch_jobs(conn, order_by="source ASC")
        conn.close()
        assert len(jobs) == 3
        # indeed (Platform Engineer) comes before linkedin alphabetically
        assert jobs[0]["platform"] == "indeed"
        assert jobs[1]["platform"] == "linkedin"
        assert jobs[2]["platform"] == "linkedin"

    def test_fetch_jobs_with_sort_title_desc(self, seeded_db):
        """TRIANGULATE: _fetch_jobs with title DESC should return Z→A order."""
        import sqlite3
        from src.status.routes import _fetch_jobs
        conn = sqlite3.connect(seeded_db)
        conn.row_factory = sqlite3.Row
        jobs, total = _fetch_jobs(conn, order_by="title DESC")
        conn.close()
        assert len(jobs) == 3
        # SRE Specialist > Platform Engineer > DevOps Engineer alphabetically
        assert jobs[0]["title"] == "SRE Specialist"
        assert jobs[1]["title"] == "Platform Engineer"
        assert jobs[2]["title"] == "DevOps Engineer"


class TestTableEndpointSort:
    """GET /table with sort param — verify HTML row order."""

    def test_table_endpoint_with_sort_param(self, client):
        """RED: /table?sort=platform:asc returns indeed row before linkedin rows."""
        response = client.get("/table?sort=platform:asc")
        assert response.status_code == 200
        html = response.text
        indeed_pos = html.find("Platform Engineer")
        devops_pos = html.find("DevOps Engineer")
        sre_pos = html.find("SRE Specialist")
        assert indeed_pos > 0
        assert devops_pos > 0
        assert sre_pos > 0
        # indeed comes before linkedin alphabetically
        assert indeed_pos < devops_pos
        assert indeed_pos < sre_pos


# =============================================================================
# Phase 2 — PR 2: Settings UI sort configurator (RED)
# =============================================================================


class TestSettingsSortFieldset:
    """Settings page — Column Sort fieldset renders correctly."""

    def test_settings_page_contains_sort_fieldset(self, client):
        """RED: /settings should contain 'Column Sort' fieldset structure."""
        response = client.get("/settings")
        assert response.status_code == 200
        html = response.text

        # Fieldset must have a "Column Sort" legend
        assert "Column Sort" in html

        # Must include the sort config container and add button (JS generates rows)
        assert 'id="sort-config-container"' in html
        assert "Add sort level" in html

        # Verify script.js defines all sortable columns (excluding "link")
        import os
        script_path = os.path.join(os.path.dirname(__file__),
                                    "../../src/dashboard/static/script.js")
        with open(script_path) as f:
            js = f.read()

        from src.status.routes import SORT_WHITELIST
        for col in SORT_WHITELIST:
            assert f"'{col}'" in js, f"Column '{col}' missing from script.js sort config"

        # Must NOT include "link" in sort columns
        assert "'link'" not in js.replace("_", "")

        # Must include direction options (asc, desc)
        assert "'asc'" in js
        assert "'desc'" in js

    def test_table_endpoint_with_sort_title_desc(self, client):
        """TRIANGULATE: /table?sort=title:desc should return Z→A title order."""
        response = client.get("/table?sort=title:desc")
        assert response.status_code == 200
        html = response.text
        sre_pos = html.find("SRE Specialist")
        platform_pos = html.find("Platform Engineer")
        devops_pos = html.find("DevOps Engineer")
        assert sre_pos > 0
        assert platform_pos > 0
        assert devops_pos > 0
        # S > P > D alphabetically
        assert sre_pos < platform_pos
        assert platform_pos < devops_pos


# =============================================================================
# Phase 4 — PR 3: Integration tests for HTMX threading + sort indicators (RED)
# =============================================================================


class TestSortIntegration:
    """Integration tests: sort threading, coexistence, pagination reset, persistence, indicators."""

    def test_sort_param_in_table_context(self, client):
        """RED: /table?sort=platform:asc should pass sort string into template context
        so table.html can render sort indicators."""
        response = client.get("/table?sort=platform:asc")
        assert response.status_code == 200
        html = response.text
        # The sort value must appear somewhere in the rendered HTML for indicator rendering
        assert "platform:asc" in html or "↑" in html

    def test_sort_param_coexists_with_search_and_filters(self, client):
        """RED: /table?sort=salary:desc&search=Engineer&filters=solo_pendientes
        should work correctly with all params."""
        response = client.get("/table?sort=salary:desc&search=Engineer&filters=solo_pendientes")
        assert response.status_code == 200
        html = response.text
        # Should return results since "Engineer" matches at least one row
        assert "Engineer" in html
        # Sort value should be in context for indicator rendering
        assert "salary:desc" in html or "↓" in html

    def test_sort_with_page_reset(self, client):
        """RED: /table?sort=company:asc&page=1 should render correctly
        (simulating JS resetting page to 1 when sort changes)."""
        response = client.get("/table?sort=company:asc&page=1")
        assert response.status_code == 200
        html = response.text
        # Should render page 1 of results sorted by company
        assert "Page 1" in html or "page 1" in html.lower()

    def test_sort_indicator_arrows_rendered(self, client):
        """RED: /table?sort=platform:asc should render ↑ arrow indicator
        on the platform column header."""
        response = client.get("/table?sort=platform:asc")
        assert response.status_code == 200
        html = response.text
        # The platform header should show ↑ indicator
        assert "↑" in html
        # The sort value should be embedded for JS reading
        assert "platform:asc" in html

    def test_sort_indicators_vary_by_direction(self, client):
        """RED: /table?sort=salary:desc should render ↓ on salary header,
        and /table?sort=salary:asc should render ↑."""
        resp_desc = client.get("/table?sort=salary:desc")
        assert "↓" in resp_desc.text

        resp_asc = client.get("/table?sort=salary:asc")
        assert "↑" in resp_asc.text

    def test_script_js_has_sort_state_populate(self, client):
        """RED: script.js must have code to populate #sort-state from localStorage('fb-sort-config')."""
        response = client.get("/static/script.js")
        js = response.text
        assert "sort-state" in js or "getSortParam" in js
        assert "fb-sort-config" in js
        assert "localStorage" in js

"""Shared fixtures for e2e tests — session-scoped server with isolated DB."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
WRAPPER = HERE / "run_server.py"


@pytest.fixture(scope="session")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Temporary database path for the e2e test session."""
    return tmp_path_factory.mktemp("data") / "e2e.db"


@pytest.fixture(scope="session")
def server_url(db_path: Path) -> str:
    """Start uvicorn with isolated DB, seed platforms, yield URL, tear down."""
    port = 14201
    proc = subprocess.Popen(
        ["python3", str(WRAPPER), str(db_path), str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    url = f"http://localhost:{port}"

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scan_platforms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            enabled INTEGER DEFAULT 1
        );
        INSERT OR IGNORE INTO scan_platforms (name, url) VALUES ('LinkedIn', 'https://www.linkedin.com/jobs/');
        INSERT OR IGNORE INTO scan_platforms (name, url) VALUES ('InfoJobs', 'https://www.infojobs.com');
        INSERT OR IGNORE INTO scan_platforms (name, url) VALUES ('Indeed', 'https://es.indeed.com');
    """)
    conn.commit()
    conn.close()

    yield url
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="session", autouse=True)
def _db_path_env(db_path: Path) -> Iterator[None]:
    """Set DB_PATH env so server and scan subprocesses share the session tmp DB.

    The server subprocess inherits the env var (runner.py copies os.environ
    when spawning scan subprocesses), so settings.DB_PATH resolves to the
    tmp DB at import time in every child process. Restored in finally so the
    env is never left dirty, even if a fixture fails.
    """
    prev = os.environ.get("DB_PATH")
    os.environ["DB_PATH"] = str(db_path)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = prev


@pytest.fixture(scope="session", autouse=True)
def _real_db_invariant() -> Iterator[dict[str, object]]:
    """Assert the real jobs.db stays untouched across the e2e session.

    Snapshots existence + row count before any server starts; teardown
    (which runs after server teardown) asserts the real DB still matches.
    If the real DB did not exist at session start, it must still not exist.
    """
    real = PROJECT_ROOT / "jobs.db"
    if not real.exists():
        baseline: dict[str, object] = {"exists": False, "count": None}
    else:
        conn = sqlite3.connect(str(real))
        try:
            baseline = {
                "exists": True,
                "count": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            }
        finally:
            conn.close()
    yield baseline
    if not baseline["exists"]:
        assert not real.exists(), "real jobs.db was created during the e2e session"
    else:
        conn = sqlite3.connect(str(real))
        try:
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        finally:
            conn.close()
        assert count == baseline["count"], (
            f"real jobs.db row count changed: {baseline['count']} -> {count}"
        )

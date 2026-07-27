"""Shared fixtures for e2e tests — session-scoped server with isolated DB."""

from __future__ import annotations

import sqlite3
import subprocess
import time
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

"""E2E: DB_PATH env-driven isolation (spec: e2e-db-isolation).

Proves the session server and its scan subprocesses operate on the
temporary session DB:
(a) a subprocess inheriting os.environ resolves DB_PATH to the tmp DB
    (same propagation mechanism runner.py uses for scan subprocesses),
(b) the tmp DB the server operates on holds the seeded platforms,
(c) the real jobs.db stays untouched (same row count as before).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from src.core.config.settings import PROJECT_ROOT

_PROBE_DB_PATH = "from src.core.config.settings import DB_PATH; print(DB_PATH)"


def test_db_path_env_propagates_to_subprocess(db_path: Path) -> None:
    """A fresh interpreter sees DB_PATH via env (runner.py:122 mechanism)."""
    env = os.environ.copy()
    out = subprocess.run(
        [sys.executable, "-c", _PROBE_DB_PATH],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert out.stdout.strip() == str(db_path)


def test_session_db_has_seeded_scan_platforms(server_url: str, db_path: Path) -> None:
    """The session server operated on the tmp DB: seeds present."""
    assert server_url
    conn = sqlite3.connect(str(db_path))
    try:
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM scan_platforms").fetchall()
        }
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
    finally:
        conn.close()
    assert {"LinkedIn", "InfoJobs", "Indeed"} <= names
    assert "jobs" in tables


def test_real_db_jobs_untouched(server_url: str, _real_db_invariant: dict[str, object]) -> None:
    """The session left the real jobs.db row count unchanged."""
    assert server_url
    real = PROJECT_ROOT / "jobs.db"
    if not _real_db_invariant["exists"]:
        assert not real.exists(), "real jobs.db was created during the session"
        return
    conn = sqlite3.connect(str(real))
    try:
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    finally:
        conn.close()
    assert count == _real_db_invariant["count"]

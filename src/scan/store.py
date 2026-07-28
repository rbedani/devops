"""SQLite store for SCAN module — scan_platforms table.

Migrated from src/datos/store.py as part of the 5-layer architecture extraction.
Uses the same jobs.db shared with the rest of the application.
"""

from __future__ import annotations

import sqlite3

from src.core.config.settings import DB_PATH as _CORE_DB_PATH
from src.scan.models import ScanPlatform


def get_connection(db_path: str = "") -> sqlite3.Connection:
    """Open a sqlite3 connection with row_factory for the scan DB."""
    path = db_path or str(_CORE_DB_PATH)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    _run_enabled_migration(conn)
    return conn


def _run_enabled_migration(conn: sqlite3.Connection) -> None:
    """Add enabled column if missing (idempotent)."""
    try:  # noqa: SIM105
        conn.execute("ALTER TABLE scan_platforms ADD COLUMN enabled INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()


def run_scan_migration(db_path: str) -> None:
    """Create scan_platforms table and seed defaults (idempotent).

    Creates the scan_platforms table if not present and seeds LinkedIn
    and InfoJobs as default scan platforms.
    """
    conn = get_connection(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scan_platforms (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT    NOT NULL UNIQUE,
                url     TEXT    NOT NULL,
                enabled INTEGER DEFAULT 1
            );
        """)
        _run_enabled_migration(conn)

        # Seed LinkedIn if not already present
        existing = conn.execute(
            "SELECT COUNT(*) FROM scan_platforms WHERE name = ?", ("LinkedIn",)
        ).fetchone()[0]
        if existing == 0:
            conn.execute(
                "INSERT INTO scan_platforms (name, url, enabled) VALUES (?, ?, 1)",
                ("LinkedIn", "https://www.linkedin.com/jobs/"),
            )

        # Seed InfoJobs if not already present
        existing_ij = conn.execute(
            "SELECT COUNT(*) FROM scan_platforms WHERE name = ?", ("InfoJobs",)
        ).fetchone()[0]
        if existing_ij == 0:
            conn.execute(
                "INSERT INTO scan_platforms (name, url, enabled) VALUES (?, ?, 1)",
                ("InfoJobs", "https://www.infojobs.net/jobsearch/search-results/list.xhtml"),
            )

        # Seed Indeed if not already present
        existing_indeed = conn.execute(
            "SELECT COUNT(*) FROM scan_platforms WHERE name = ?", ("Indeed",)
        ).fetchone()[0]
        if existing_indeed == 0:
            conn.execute(
                "INSERT INTO scan_platforms (name, url, enabled) VALUES (?, ?, 1)",
                ("Indeed", "https://es.indeed.com"),
            )

        # Seed Tecnoempleo if not already present
        existing_te = conn.execute(
            "SELECT COUNT(*) FROM scan_platforms WHERE name = ?", ("Tecnoempleo",)
        ).fetchone()[0]
        if existing_te == 0:
            conn.execute(
                "INSERT INTO scan_platforms (name, url, enabled) VALUES (?, ?, 1)",
                ("Tecnoempleo", "https://www.tecnoempleo.com/ofertas-trabajo/"),
            )

        # Seed Welcome to the Jungle if not already present
        existing_wttj = conn.execute(
            "SELECT COUNT(*) FROM scan_platforms WHERE name = ?", ("Welcome to the Jungle",)
        ).fetchone()[0]
        if existing_wttj == 0:
            conn.execute(
                "INSERT INTO scan_platforms (name, url, enabled) VALUES (?, ?, 1)",
                ("Welcome to the Jungle", "https://www.welcometothejungle.com/en/jobs"),
            )

        conn.commit()
    except (sqlite3.OperationalError, sqlite3.IntegrityError):
        conn.rollback()
    finally:
        conn.close()


def get_platforms(conn: sqlite3.Connection) -> list[ScanPlatform]:
    """Return all scan platforms ordered by name."""
    rows = conn.execute(
        "SELECT id, name, url, enabled FROM scan_platforms ORDER BY name"
    ).fetchall()
    return [
        ScanPlatform(
            name=row["name"],
            url=row["url"],
            id=row["id"],
            enabled=bool(row["enabled"]),
        )
        for row in rows
    ]


def get_enabled_platform_names(conn: sqlite3.Connection) -> list[str]:
    """Return names of enabled platforms only."""
    rows = conn.execute(
        "SELECT name FROM scan_platforms WHERE enabled = 1 ORDER BY name"
    ).fetchall()
    return [row["name"] for row in rows]


def add_platform(conn: sqlite3.Connection, name: str, url: str) -> int:
    """Insert a new platform. Returns the row id. Raises IntegrityError on duplicate name."""
    cursor = conn.execute(
        "INSERT INTO scan_platforms (name, url, enabled) VALUES (?, ?, 1)",
        (name, url),
    )
    conn.commit()
    row_id = cursor.lastrowid
    assert row_id is not None
    return row_id


def remove_platform(conn: sqlite3.Connection, platform_id: int) -> bool:
    """Delete a platform by id. Returns True if a row was deleted."""
    cursor = conn.execute("DELETE FROM scan_platforms WHERE id = ?", (platform_id,))
    conn.commit()
    return cursor.rowcount > 0


def toggle_platform(conn: sqlite3.Connection, platform_id: int) -> bool | None:
    """Toggle enabled/disabled for a platform. Returns new enabled state or None if not found."""
    row = conn.execute(
        "SELECT enabled FROM scan_platforms WHERE id = ?", (platform_id,)
    ).fetchone()
    if row is None:
        return None
    new_state = 0 if row["enabled"] else 1
    conn.execute(
        "UPDATE scan_platforms SET enabled = ? WHERE id = ?", (new_state, platform_id)
    )
    conn.commit()
    return bool(new_state)
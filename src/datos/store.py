"""SQLite store for datos module — profile_fields, cv_files tables.

All tables live in the same jobs.db file shared with the dashboard server.
Migrations are additive and idempotent (CREATE TABLE IF NOT EXISTS).
The scan_platforms table has been moved to src.scan.store as part of the
5-layer architecture extraction.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from src.core.config.settings import DB_PATH as _CORE_DB_PATH
from src.datos.models import CVFile, ProfileField


def get_connection(db_path: str = "") -> sqlite3.Connection:
    """Open a sqlite3 connection with row_factory for the datos DB."""
    path = db_path or str(_CORE_DB_PATH)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def run_datos_migration(db_path: str) -> None:
    """Create datos tables and seed defaults (idempotent).

    Creates profile_fields and cv_files tables.
    The scan_platforms table is now managed by src.scan.store.
    """
    conn = get_connection(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profile_fields (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL DEFAULT '',
                field_type  TEXT    NOT NULL DEFAULT 'text',
                value       TEXT    NOT NULL DEFAULT '',
                position    INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS cv_files (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                filename      TEXT    NOT NULL,
                original_name TEXT    NOT NULL,
                file_path     TEXT    NOT NULL,
                uploaded_at   TEXT    NOT NULL
            );
        """)
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.IntegrityError):
        conn.rollback()
    finally:
        conn.close()


# -- Profile Fields CRUD --------------------------------------------------------

# (rest of CRUD follows here — unchanged)


def get_fields(conn: sqlite3.Connection) -> list[ProfileField]:
    """Return all profile fields ordered by position."""
    rows = conn.execute(
        "SELECT id, name, field_type, value, position FROM profile_fields ORDER BY position"
    ).fetchall()
    return [
        ProfileField(
            name=row["name"],
            field_type=row["field_type"],
            value=row["value"],
            position=row["position"],
            id=row["id"],
        )
        for row in rows
    ]


def save_fields(conn: sqlite3.Connection, fields: list[dict[str, Any]]) -> None:
    """Persist multiple fields in a single transaction."""
    conn.execute("BEGIN")
    try:
        for f in fields:
            conn.execute(
                "UPDATE profile_fields SET name=?, field_type=?, value=?, position=? WHERE id=?",
                (f.get("name", ""), f.get("field_type", "text"),
                 f.get("value", ""), f.get("position", 0), f["id"]),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def add_field(conn: sqlite3.Connection, field_type: str = "text") -> ProfileField:
    """Insert a new empty field and return it with the generated id."""
    cursor = conn.execute(
        "INSERT INTO profile_fields (name, field_type, value, position) VALUES ('', ?, '', 0)",
        (field_type,),
    )
    conn.commit()
    field_id = cursor.lastrowid
    return ProfileField(name="", field_type=field_type, value="", position=0, id=field_id)


def remove_field(conn: sqlite3.Connection, field_id: int) -> bool:
    """Delete a field by id. Returns True if a row was deleted."""
    cursor = conn.execute("DELETE FROM profile_fields WHERE id = ?", (field_id,))
    conn.commit()
    return cursor.rowcount > 0


# -- CV Files CRUD --------------------------------------------------------------


def get_cv(conn: sqlite3.Connection) -> CVFile | None:
    """Return the most recent CV record, or None if none exists."""
    row = conn.execute(
        "SELECT id, filename, original_name, file_path, uploaded_at FROM cv_files ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return CVFile(
        filename=row["filename"],
        original_name=row["original_name"],
        file_path=row["file_path"],
        uploaded_at=row["uploaded_at"],
        id=row["id"],
    )


def save_cv(conn: sqlite3.Connection, filename: str, original_name: str, file_path: str) -> int:
    """Insert a CV record. Returns the row id."""
    from datetime import datetime, timezone
    uploaded_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO cv_files (filename, original_name, file_path, uploaded_at) VALUES (?, ?, ?, ?)",
        (filename, original_name, file_path, uploaded_at),
    )
    conn.commit()
    row_id = cursor.lastrowid
    assert row_id is not None
    return row_id


def delete_cv(conn: sqlite3.Connection) -> bool:
    """Delete all CV records. Returns True if any row was deleted."""
    cursor = conn.execute("DELETE FROM cv_files")
    conn.commit()
    return cursor.rowcount > 0
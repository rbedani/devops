"""SQLite database layer for job listings — singleton pattern.

Use `get_db()` to obtain the shared JobDatabase instance. Migration is
separated from connection so it only runs once at startup.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from src.core.config.settings import DB_PATH
from src.core.models.job import Job


def _content_hash(title: str, company: str | None, description: str | None) -> str:
    """Compute SHA-256 of combined job content for dedup."""
    raw = f"{title}{company or ''}{description or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _run_content_hash_migration(conn: sqlite3.Connection) -> None:
    """Add content_hash column and unique index if not present (idempotent).

    Uses CREATE UNIQUE INDEX so that ON CONFLICT(content_hash) works in upsert.
    """
    try:  # noqa: SIM105
        conn.execute("ALTER TABLE jobs ADD COLUMN content_hash TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:  # noqa: SIM105
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_content_hash ON jobs(content_hash)")  # noqa: E501
    except sqlite3.OperationalError:
        pass  # Index already exists
    conn.commit()


def _run_status_migration(conn: sqlite3.Connection) -> None:
    """Add status column if missing (idempotent)."""
    try:  # noqa: SIM105
        conn.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()


def _run_indeed_tag_migration(conn: sqlite3.Connection) -> None:
    """Rename 'salary' → 'salario' in Indeed job tags JSON.

    Indeed scraper previously used 'salary' as the tag key; the rest of the
    codebase uses 'salario'. This migration is idempotent.
    """
    rows = conn.execute(
        "SELECT id, tags FROM jobs WHERE source = 'indeed'"
    ).fetchall()
    for row in rows:
        row_id, tags_raw = row[0], row[1] or "[]"
        tags = json.loads(tags_raw)
        changed = False
        for tag in tags:
            if tag.get("key") == "salary":
                tag["key"] = "salario"
                changed = True
        if changed:
            conn.execute(
                "UPDATE jobs SET tags = ? WHERE id = ?",
                (json.dumps(tags), row_id),
            )
    conn.commit()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    url         TEXT    NOT NULL UNIQUE,
    company     TEXT,
    location    TEXT,
    description TEXT,
    tags        TEXT    DEFAULT '[]',
    scraped_at  TEXT    NOT NULL,
    status      TEXT    DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
"""


def run_migrations(db_path: Path | str | None = None) -> None:
    """Run schema migrations independently of connection.

    Call this once at application startup. Subsequent calls are idempotent.
    """
    path = Path(db_path) if db_path else DB_PATH
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SCHEMA)
        _run_status_migration(conn)
        _run_content_hash_migration(conn)
        _run_indeed_tag_migration(conn)
    finally:
        conn.close()


def update_job_status(job_id: int, status: str, db_path: Path | str | None = None) -> bool:
    """Set the status column for a job row. Returns True if row existed.

    Standalone utility — avoids duplicating this logic across route modules.
    """
    path = Path(db_path) if db_path else DB_PATH
    conn = sqlite3.connect(str(path))
    try:
        cursor = conn.execute(
            "UPDATE jobs SET status = ? WHERE id = ?", (status, job_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


class JobDatabase:
    """Thin wrapper around SQLite for storing and querying job listings."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._conn: sqlite3.Connection | None = None

    # -- Connection management ---------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> JobDatabase:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # -- CRUD -------------------------------------------------------------------

    def upsert_job(self, job: Job) -> int:
        """Insert or update a job (matched by URL or content_hash). Returns the row id."""
        conn = self.connect()
        tags_json = json.dumps(
            [{"key": t.key, "value": t.value, "confidence": t.confidence} for t in job.tags]
        )

        h = _content_hash(job.title, job.company, job.description)

        # Check if same content exists under a different URL
        existing = conn.execute(
            "SELECT id FROM jobs WHERE content_hash = ?", (h,)
        ).fetchone()

        if existing:
            # Update existing row with new URL and data
            cursor = conn.execute(
                """
                UPDATE jobs SET
                    source = ?, title = ?, url = ?, company = ?, location = ?,
                    description = ?, tags = ?, scraped_at = ?, content_hash = ?
                WHERE id = ?
                """,
                (
                    job.source, job.title, job.url, job.company, job.location,
                    job.description, tags_json, job.scraped_at.isoformat(), h,
                    existing[0],
                ),
            )
            conn.commit()
            return existing[0]
        else:
            cursor = conn.execute(
                """
                INSERT INTO jobs (source, title, url, company, location, description, tags, scraped_at, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title       = excluded.title,
                    company     = excluded.company,
                    location    = excluded.location,
                    description = excluded.description,
                    tags        = excluded.tags,
                    scraped_at  = excluded.scraped_at,
                    content_hash = excluded.content_hash
                """,  # noqa: E501
                (
                    job.source,
                    job.title,
                    job.url,
                    job.company,
                    job.location,
                    job.description,
                    tags_json,
                    job.scraped_at.isoformat(),
                    h,
                ),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def upsert_many(self, jobs: Sequence[Job]) -> list[int]:
        """Batch upsert. Returns list of row ids."""
        return [self.upsert_job(j) for j in jobs]

    def get_job_by_url(self, url: str) -> Job | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
        return Job.from_row(row) if row else None

    def get_all(self, source: str | None = None, limit: int = 100) -> list[Job]:
        conn = self.connect()
        if source:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE source = ? ORDER BY scraped_at DESC LIMIT ?",
                (source, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY scraped_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Job.from_row(r) for r in rows]

    def count(self, source: str | None = None) -> int:
        conn = self.connect()
        if source:
            row = conn.execute("SELECT COUNT(*) FROM jobs WHERE source = ?", (source,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
        return row[0]  # type: ignore[index]

    def search_by_tag(self, key: str, value: str) -> list[Job]:
        """Search jobs where a specific tag contains the given value."""
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE tags LIKE ? ORDER BY scraped_at DESC",
            (f'%{key}%{value}%',),
        ).fetchall()
        return [Job.from_row(r) for r in rows]

    def delete_job(self, url: str) -> bool:
        conn = self.connect()
        cursor = conn.execute("DELETE FROM jobs WHERE url = ?", (url,))
        conn.commit()
        return cursor.rowcount > 0

    def delete_all(self) -> int:
        """Delete all rows from the jobs table. Returns number of rows deleted."""
        conn = self.connect()
        cursor = conn.execute("DELETE FROM jobs")
        conn.commit()
        return cursor.rowcount

    def update_status(self, job_id: int, status: str) -> None:
        """Set the status column for a job row.

        Accepts any status string (including empty string to clear).
        Preserves all other columns.
        """
        conn = self.connect()
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        conn.commit()


# -- Singleton accessor -------------------------------------------------------

_instance: JobDatabase | None = None


def get_db(db_path: Path | str | None = None) -> JobDatabase:
    """Return the shared JobDatabase singleton.

    The database is created on first call and cached. connect() is deliberately
    NOT called here — callers must call connect() explicitly or use the context
    manager. This allows the caller to control when the connection is established
    (e.g. after running migrations).
    """
    global _instance
    if _instance is None:
        _instance = JobDatabase(db_path=db_path)
    return _instance
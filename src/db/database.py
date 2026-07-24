"""SQLite database layer for job listings."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Sequence

from src.models.job import Job, JobTag


DEFAULT_DB_PATH = Path("jobs.db")

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
    scraped_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
"""


class JobDatabase:
    """Thin wrapper around SQLite for storing and querying job listings."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # -- Connection management ---------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
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
        """Insert or update a job (matched by URL). Returns the row id."""
        conn = self.connect()
        tags_json = json.dumps(
            [{"key": t.key, "value": t.value, "confidence": t.confidence} for t in job.tags]
        )

        cursor = conn.execute(
            """
            INSERT INTO jobs (source, title, url, company, location, description, tags, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title       = excluded.title,
                company     = excluded.company,
                location    = excluded.location,
                description = excluded.description,
                tags        = excluded.tags,
                scraped_at  = excluded.scraped_at
            """,
            (
                job.source,
                job.title,
                job.url,
                job.company,
                job.location,
                job.description,
                tags_json,
                job.scraped_at.isoformat(),
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

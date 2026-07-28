"""Unit tests for SQLite database layer."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.models.job import Job
from src.core.db.database import JobDatabase, run_migrations


@pytest.fixture
def tmp_db(tmp_path: Path) -> JobDatabase:
    """Create a temporary DB for testing."""
    db_path = tmp_path / "test_jobs.db"
    run_migrations(db_path)
    return JobDatabase(db_path)


class TestJobDatabase:
    def test_connect_creates_schema(self, tmp_db: JobDatabase):
        tmp_db.connect()
        # Verify table exists
        rows = tmp_db._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [r["name"] for r in rows]
        assert "jobs" in table_names
        tmp_db.close()

    def test_upsert_and_get(self, tmp_db: JobDatabase):
        job = Job(
            source="linkedin",
            title="DevOps Engineer",
            url="https://linkedin.com/jobs/123",
            company="Acme Corp",
            location="Buenos Aires",
        )
        job.set_tag("modalidad", "Remoto", 0.9)

        with tmp_db:
            row_id = tmp_db.upsert_job(job)
            assert row_id is not None

            fetched = tmp_db.get_job_by_url("https://linkedin.com/jobs/123")
            assert fetched is not None
            assert fetched.title == "DevOps Engineer"
            assert fetched.company == "Acme Corp"
            assert fetched.get_tag("modalidad") == "Remoto"

    def test_upsert_updates_on_duplicate_url(self, tmp_db: JobDatabase):
        job1 = Job(source="test", title="Old Title", url="http://x/1")
        job2 = Job(source="test", title="New Title", url="http://x/1")

        with tmp_db:
            tmp_db.upsert_job(job1)
            tmp_db.upsert_job(job2)

            fetched = tmp_db.get_job_by_url("http://x/1")
            assert fetched is not None
            assert fetched.title == "New Title"
            assert tmp_db.count() == 1

    def test_get_all(self, tmp_db: JobDatabase):
        with tmp_db:
            for i in range(5):
                tmp_db.upsert_job(Job(source="test", title=f"Job {i}", url=f"http://x/{i}"))

            jobs = tmp_db.get_all()
            assert len(jobs) == 5

    def test_get_all_by_source(self, tmp_db: JobDatabase):
        with tmp_db:
            tmp_db.upsert_job(Job(source="linkedin", title="L1", url="http://x/1"))
            tmp_db.upsert_job(Job(source="indeed", title="I1", url="http://x/2"))
            tmp_db.upsert_job(Job(source="linkedin", title="L2", url="http://x/3"))

            linkedin_jobs = tmp_db.get_all(source="linkedin")
            assert len(linkedin_jobs) == 2

    def test_count(self, tmp_db: JobDatabase):
        with tmp_db:
            assert tmp_db.count() == 0
            tmp_db.upsert_job(Job(source="test", title="J", url="http://x"))
            assert tmp_db.count() == 1

    def test_delete_job(self, tmp_db: JobDatabase):
        job = Job(source="test", title="Delete Me", url="http://x/del")
        with tmp_db:
            tmp_db.upsert_job(job)
            assert tmp_db.count() == 1

            result = tmp_db.delete_job("http://x/del")
            assert result is True
            assert tmp_db.count() == 0

    def test_delete_nonexistent_returns_false(self, tmp_db: JobDatabase):
        with tmp_db:
            assert tmp_db.delete_job("http://nonexistent") is False

    def test_context_manager(self, tmp_path: Path):
        db_path = tmp_path / "ctx.db"
        run_migrations(db_path)
        with JobDatabase(db_path) as db:
            db.upsert_job(Job(source="test", title="J", url="http://x"))
        # Should be closed after context
        assert db._conn is None

    # -- Status methods (Task 1.2) ------------------------------------------

    def test_update_status_sets_value(self, tmp_db: JobDatabase):
        """RED: update_status should set the status column."""
        with tmp_db:
            row_id = tmp_db.upsert_job(Job(source="test", title="Job A", url="http://x/1"))
            tmp_db.update_status(row_id, "postulado")

            fetched = tmp_db.get_job_by_url("http://x/1")
            assert fetched is not None
            assert fetched.status == "postulado"

    def test_update_status_empty_string(self, tmp_db: JobDatabase):
        """RED: update_status should allow setting empty string status."""
        with tmp_db:
            row_id = tmp_db.upsert_job(Job(source="test", title="Job B", url="http://x/2"))
            tmp_db.update_status(row_id, "postulado")
            tmp_db.update_status(row_id, "")

            fetched = tmp_db.get_job_by_url("http://x/2")
            assert fetched is not None
            assert fetched.status == ""

    def test_update_status_preserves_other_columns(self, tmp_db: JobDatabase):
        """TRIANGULATE: update_status should not affect other columns."""
        with tmp_db:
            row_id = tmp_db.upsert_job(Job(
                source="linkedin", title="DevOps Engineer",
                url="http://x/3", company="Acme",
            ))
            tmp_db.update_status(row_id, "general-error")

            fetched = tmp_db.get_job_by_url("http://x/3")
            assert fetched is not None
            assert fetched.status == "general-error"
            assert fetched.title == "DevOps Engineer"
            assert fetched.company == "Acme"

    def test_delete_all_clears_table(self, tmp_db: JobDatabase):
        """RED: delete_all should remove all rows and return deleted count."""
        with tmp_db:
            for i in range(3):
                tmp_db.upsert_job(Job(source="test", title=f"Job {i}", url=f"http://x/{i}"))
            assert tmp_db.count() == 3
            deleted = tmp_db.delete_all()
            assert deleted == 3
            assert tmp_db.count() == 0

    def test_delete_all_empty_table_returns_zero(self, tmp_db: JobDatabase):
        """TRIANGULATE: delete_all on empty table should return 0."""
        with tmp_db:
            assert tmp_db.count() == 0
            deleted = tmp_db.delete_all()
            assert deleted == 0
            assert tmp_db.count() == 0


# =============================================================================
# Task 2.1 — _run_indeed_tag_migration
# =============================================================================


class TestIndeedTagMigration:
    """RED: _run_indeed_tag_migration renames 'salary' → 'salario' in tags JSON."""

    def _insert_indeed_job_with_salary_key(self, db_path: Path) -> int:
        """Helper: insert an Indeed job with 'salary' key in tags JSON."""
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO jobs (source, title, url, company, tags, scraped_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "indeed",
                "Test Job",
                "http://indeed.com/viewjob?jk=test123",
                "TestCo",
                json.dumps([{"key": "salary", "value": "50000 EUR", "confidence": 0.9}]),
                "2025-01-01T00:00:00",
            ),
        )
        conn.commit()
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return row_id

    def test_migration_renames_salary_to_salario(self, tmp_path: Path):
        """RED: migration should rename 'salary' key to 'salario' in tags."""
        from src.core.db.database import _run_indeed_tag_migration

        db_path = tmp_path / "test_jobs.db"
        run_migrations(db_path)
        self._insert_indeed_job_with_salary_key(db_path)

        conn = sqlite3.connect(str(db_path))
        _run_indeed_tag_migration(conn)

        row = conn.execute("SELECT tags FROM jobs WHERE source = 'indeed'").fetchone()
        tags = json.loads(row[0])
        tag_keys = [t["key"] for t in tags]
        assert "salario" in tag_keys, f"Expected 'salario' key, got: {tag_keys}"
        assert "salary" not in tag_keys, f"Old 'salary' key should be gone, got: {tag_keys}"
        assert tags[0]["value"] == "50000 EUR"
        conn.close()

    def test_migration_is_idempotent(self, tmp_path: Path):
        """TRIANGULATE: running migration twice should not change the result."""
        from src.core.db.database import _run_indeed_tag_migration

        db_path = tmp_path / "test_jobs.db"
        run_migrations(db_path)
        self._insert_indeed_job_with_salary_key(db_path)

        conn = sqlite3.connect(str(db_path))
        _run_indeed_tag_migration(conn)
        _run_indeed_tag_migration(conn)  # second run — should be no-op

        row = conn.execute("SELECT tags FROM jobs WHERE source = 'indeed'").fetchone()
        tags = json.loads(row[0])
        assert tags[0]["key"] == "salario"
        assert tags[0]["value"] == "50000 EUR"
        conn.close()

    def test_migration_skips_jobs_without_salary_key(self, tmp_path: Path):
        """TRIANGULATE: jobs without 'salary' key should be untouched."""
        from src.core.db.database import _run_indeed_tag_migration

        db_path = tmp_path / "test_jobs.db"
        run_migrations(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO jobs (source, title, url, company, tags, scraped_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "indeed",
                "No Salary Job",
                "http://indeed.com/viewjob?jk=nosalary",
                "TestCo",
                json.dumps([{"key": "modalidad", "value": "Remoto", "confidence": 0.9}]),
                "2025-01-01T00:00:00",
            ),
        )
        conn.commit()

        _run_indeed_tag_migration(conn)

        row = conn.execute("SELECT tags FROM jobs WHERE url = 'http://indeed.com/viewjob?jk=nosalary'").fetchone()
        tags = json.loads(row[0])
        assert tags[0]["key"] == "modalidad"
        assert tags[0]["value"] == "Remoto"
        conn.close()


# =============================================================================
# Task 3.1 — Content-hash migration not called per-upsert
# =============================================================================


class TestContentHashMigrationNotPerUpsert:
    """RED: _run_content_hash_migration should NOT be called inside upsert_job()."""

    def test_upsert_does_not_call_content_hash_migration(self, tmp_path: Path):
        """upsert_job 100x should never trigger _run_content_hash_migration."""
        db_path = tmp_path / "test_jobs.db"
        run_migrations(db_path)
        db = JobDatabase(db_path)
        db.connect()

        with patch("src.core.db.database._run_content_hash_migration") as mock_migration:
            for i in range(100):
                db.upsert_job(Job(
                    source="test",
                    title=f"Job {i}",
                    url=f"http://example.com/job/{i}",
                ))
            mock_migration.assert_not_called()

        db.close()


# =============================================================================
# Task 4.1 — update_job_status shared utility
# =============================================================================


class TestUpdateJobStatus:
    """RED: update_job_status standalone function in database.py."""

    def test_updates_existing_job_status(self, tmp_path: Path):
        """Insert a job, call update_job_status, assert status is set."""
        from src.core.db.database import update_job_status

        db_path = tmp_path / "test_jobs.db"
        run_migrations(db_path)
        db = JobDatabase(db_path)
        db.connect()
        row_id = db.upsert_job(Job(source="test", title="Job A", url="http://x/1"))
        db.close()

        result = update_job_status(row_id, "postulado", db_path)
        assert result is True

        db2 = JobDatabase(db_path)
        db2.connect()
        fetched = db2.get_job_by_url("http://x/1")
        assert fetched is not None
        assert fetched.status == "postulado"
        db2.close()

    def test_nonexistent_id_returns_false(self, tmp_path: Path):
        """update_job_status with nonexistent ID should return False."""
        from src.core.db.database import update_job_status

        db_path = tmp_path / "test_jobs.db"
        run_migrations(db_path)

        result = update_job_status(99999, "postulado", db_path)
        assert result is False

    def test_update_to_empty_status(self, tmp_path: Path):
        """TRIANGULATE: update_job_status should allow clearing status."""
        from src.core.db.database import update_job_status

        db_path = tmp_path / "test_jobs.db"
        run_migrations(db_path)
        db = JobDatabase(db_path)
        db.connect()
        row_id = db.upsert_job(Job(source="test", title="Job B", url="http://x/2"))
        db.close()

        update_job_status(row_id, "postulado", db_path)
        update_job_status(row_id, "", db_path)

        db2 = JobDatabase(db_path)
        db2.connect()
        fetched = db2.get_job_by_url("http://x/2")
        assert fetched is not None
        assert fetched.status == ""
        db2.close()

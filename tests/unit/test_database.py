"""Unit tests for SQLite database layer."""

import json
import tempfile
from pathlib import Path

import pytest

from src.models.job import Job, JobTag
from src.db.database import JobDatabase


@pytest.fixture
def tmp_db(tmp_path: Path) -> JobDatabase:
    """Create a temporary in-memory-like DB for testing."""
    db_path = tmp_path / "test_jobs.db"
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

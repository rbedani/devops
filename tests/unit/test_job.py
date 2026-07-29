"""Unit tests for Job model and tag system."""

import json
import pytest

from src.core.models.job import Job, JobTag


class TestJobTag:
    def test_key_is_normalized(self):
        tag = JobTag(key="  Modalidad  ", value="Remoto")
        assert tag.key == "modalidad"

    def test_value_is_stripped(self):
        tag = JobTag(key="salario", value="  USD 50k  ")
        assert tag.value == "USD 50k"


class TestJob:
    def test_create_minimal_job(self):
        job = Job(source="linkedin", title="DevOps Engineer", url="https://example.com/1")
        assert job.source == "linkedin"
        assert job.title == "DevOps Engineer"
        assert job.tags == []

    def test_set_and_get_tag(self):
        job = Job(source="test", title="Job", url="http://x")
        job.set_tag("modalidad", "Remoto", 0.9)
        assert job.get_tag("modalidad") == "Remoto"
        assert job.modality == "Remoto"

    def test_set_tag_replaces_existing(self):
        job = Job(source="test", title="Job", url="http://x")
        job.set_tag("modalidad", "Presencial")
        job.set_tag("modalidad", "Remoto")
        assert job.get_tag("modalidad") == "Remoto"
        assert len(job.tags) == 1

    def test_get_missing_tag_returns_none(self):
        job = Job(source="test", title="Job", url="http://x")
        assert job.get_tag("modalidad") is None
        assert job.modality is None

    def test_to_dict(self):
        job = Job(source="test", title="Job", url="http://x")
        job.set_tag("modalidad", "Remoto")
        d = job.to_dict()
        assert d["source"] == "test"
        assert len(d["tags"]) == 1
        assert d["tags"][0]["key"] == "modalidad"

    def test_repr(self):
        job = Job(source="test", title="Job", url="http://x", company="Acme")
        r = repr(job)
        assert "test" in r
        assert "Job" in r
        assert "Acme" in r

    # -- Status field (Task 1.3) -------------------------------------------

    def test_status_defaults_to_empty(self):
        """RED: a new Job should have empty string status."""
        job = Job(source="test", title="Job", url="http://x")
        assert job.status == ""

    def test_status_can_be_set(self):
        """RED: status should be settable via constructor."""
        job = Job(source="test", title="Job", url="http://x", status="postulado")
        assert job.status == "postulado"

    def test_status_in_to_dict(self):
        """RED: to_dict should include status."""
        job = Job(source="test", title="Job", url="http://x", status="postulado")
        d = job.to_dict()
        assert d["status"] == "postulado"

    def test_tags_read_from_row_empty_default(self, tmp_path):
        """Approval: from_row should use '[]' default when row has no tags column."""
        import sqlite3
        db_path = tmp_path / "test_tags_empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE jobs ("
            "id INTEGER PRIMARY KEY, source TEXT, title TEXT, url TEXT, "
            "company TEXT, location TEXT, description TEXT, tags TEXT DEFAULT '[]', "
            "scraped_at TEXT, status TEXT DEFAULT ''"
            ")"
        )
        conn.execute(
            "INSERT INTO jobs (source, title, url, company, scraped_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("linkedin", "DevOps", "http://x/1", "Acme", "2024-01-15T10:00:00"),
        )
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id = 1").fetchone()
        conn.close()

        job = Job.from_row(row)
        assert job.tags == []

    def test_status_read_from_row(self, tmp_path):
        """RED: from_row should read the status column."""
        import sqlite3
        db_path = tmp_path / "test_status.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, source TEXT, title TEXT, url TEXT, company TEXT, location TEXT, description TEXT, tags TEXT DEFAULT '[]', scraped_at TEXT, status TEXT DEFAULT '')")
        conn.execute(
            "INSERT INTO jobs (source, title, url, company, scraped_at, status) VALUES (?, ?, ?, ?, ?, ?)",
            ("linkedin", "DevOps", "http://x/1", "Acme", "2024-01-15T10:00:00", "postulado"),
        )
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id = 1").fetchone()
        conn.close()

        job = Job.from_row(row)
        assert job.status == "postulado"
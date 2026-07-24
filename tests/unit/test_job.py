"""Unit tests for Job model and tag system."""

import json
import pytest

from src.models.job import Job, JobTag


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

"""Unit tests for Telegram alert formatter."""

import pytest

from src.core.models.job import Job
from src.alerts.telegram import format_job_alert, format_jobs_table, format_jobs_markdown_table


@pytest.fixture
def sample_job() -> Job:
    job = Job(
        source="linkedin",
        title="Senior DevOps Engineer",
        url="https://linkedin.com/jobs/12345",
        company="TechCorp",
        location="Buenos Aires, Argentina",
    )
    job.set_tag("modalidad", "Remoto", 0.9)
    job.set_tag("salario", "USD 80k-100k", 0.85)
    job.set_tag("horario", "Tiempo completo", 0.8)
    job.set_tag("fecha_publicacion", "2026-07-20", 1.0)
    job.set_tag("postulados", "42", 0.9)
    return job


class TestFormatJobAlert:
    def test_contains_title(self, sample_job: Job):
        alert = format_job_alert(sample_job)
        assert "Senior DevOps Engineer" in alert

    def test_contains_company(self, sample_job: Job):
        alert = format_job_alert(sample_job)
        assert "TechCorp" in alert

    def test_contains_link(self, sample_job: Job):
        alert = format_job_alert(sample_job)
        assert "linkedin.com/jobs/12345" in alert

    def test_contains_tags(self, sample_job: Job):
        alert = format_job_alert(sample_job)
        assert "Remoto" in alert
        assert "USD 80k-100k" in alert


class TestFormatJobsTable:
    def test_empty_list(self):
        result = format_jobs_table([])
        assert "No se encontraron ofertas" in result

    def test_multiple_jobs(self):
        jobs = [
            Job(source="test", title=f"Job {i}", url=f"http://x/{i}", company=f"Company {i}")
            for i in range(3)
        ]
        result = format_jobs_table(jobs, title="Test Results")
        assert "Test Results" in result
        assert "3 oferta(s)" in result
        assert "Job 0" in result
        assert "Job 2" in result

    def test_with_tags(self, sample_job: Job):
        result = format_jobs_table([sample_job])
        assert "Remoto" in result


class TestFormatMarkdownTable:
    def test_empty(self):
        result = format_jobs_markdown_table([])
        assert "Sin resultados" in result

    def test_single_job(self, sample_job: Job):
        result = format_jobs_markdown_table([sample_job])
        assert "Senior DevOps Engineer" in result
        assert "TechCorp" in result
        assert "Buenos Aires" in result

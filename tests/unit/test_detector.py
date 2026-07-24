"""Unit tests for tag auto-detection engine."""

import pytest

from src.tags.detector import (
    TagRegistry,
    build_default_registry,
    _detect_modality,
    _detect_schedule,
    _detect_salary,
    _detect_vacancies,
    _detect_applicants,
)


class TestDetectModality:
    def test_remote_english(self):
        result = _detect_modality("Remote DevOps Engineer", "", {})
        assert any(v == "Remoto" for v, _ in result)

    def test_remote_spanish(self):
        result = _detect_modality("DevOps en teletrabajo", "", {})
        assert any(v == "Remoto" for v, _ in result)

    def test_hybrid(self):
        result = _detect_modality("DevOps Engineer", "Modalidad híbrida", {})
        assert any(v == "Híbrido" for v, _ in result)

    def test_onsite(self):
        result = _detect_modality("DevOps presencial", "", {})
        assert any(v == "Presencial" for v, _ in result)

    def test_no_match(self):
        result = _detect_modality("DevOps Engineer", "Great team", {})
        assert len(result) == 0


class TestDetectSchedule:
    def test_full_time(self):
        result = _detect_schedule("DevOps", "Full-time position", {})
        assert any(v == "Tiempo completo" for v, _ in result)

    def test_part_time(self):
        result = _detect_schedule("DevOps", "part-time contract", {})
        assert any(v == "Medio tiempo" for v, _ in result)

    def test_contract(self):
        result = _detect_schedule("DevOps", "contrato por 6 meses", {})
        assert any(v == "Contrato" for v, _ in result)


class TestDetectSalary:
    def test_usd_salary(self):
        result = _detect_salary("DevOps", "Salary: USD 80,000 - 100,000", {})
        assert len(result) > 0

    def test_dollar_salary(self):
        result = _detect_salary("DevOps", "Salario: $50.000", {})
        assert len(result) > 0

    def test_no_salary(self):
        result = _detect_salary("DevOps", "Great benefits", {})
        assert len(result) == 0


class TestDetectVacants:
    def test_spanish(self):
        result = _detect_vacancies("DevOps", "3 vacantes disponibles", {})
        assert ("3", 0.9) in result

    def test_english(self):
        result = _detect_vacancies("DevOps", "5 openings available", {})
        assert ("5", 0.9) in result


class TestDetectApplicants:
    def test_from_metadata(self):
        result = _detect_applicants("", "", {"applicants": "142"})
        assert ("142", 1.0) in result

    def test_from_text(self):
        result = _detect_applicants("", "35 personas se postularon", {})
        assert len(result) > 0


class TestTagRegistry:
    def test_default_registry_has_all_tags(self):
        reg = build_default_registry()
        assert len(reg) >= 5
        keys = reg.registered_keys
        assert "modalidad" in keys
        assert "salario" in keys
        assert "horario" in keys

    def test_custom_detector(self):
        reg = TagRegistry()

        def extract_industry(title: str, desc: str, meta: dict) -> list[tuple[str, float]]:
            text = f"{title} {desc}".lower()
            if "fintech" in text:
                return [("Fintech", 0.95)]
            return []

        reg.register("industria", extract_industry)
        tags = reg.detect_all("Fintech DevOps", "", {})
        assert len(tags) == 1
        assert tags[0].key == "industria"
        assert tags[0].value == "Fintech"

    def test_detect_all_no_duplicates(self):
        reg = build_default_registry()
        tags = reg.detect_all("Remote DevOps", "Full-time, $80k USD", {})
        keys = [t.key for t in tags]
        assert len(keys) == len(set(keys))

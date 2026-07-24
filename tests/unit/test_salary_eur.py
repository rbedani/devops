"""Unit tests for salary normalisation and format."""

import pytest

from src.tags.detector import _detect_salary


class TestSalaryDetectionEUR:
    """European salary patterns (most common in Spain/EU job boards)."""

    def test_eur_range_with_keyword(self):
        result = _detect_salary("DevOps", "Salario: 45.000€ - 55.000€ bruto anual", {})
        assert len(result) >= 1
        assert any("45" in v for v, _ in result)

    def test_eur_range_plain(self):
        result = _detect_salary("DevOps", "Salary range €60,000 - €80,000 per year", {})
        assert len(result) >= 1

    def test_eur_with_k_suffix(self):
        result = _detect_salary("DevOps", "Compensación: 50k-65k EUR", {})
        assert len(result) >= 1
        assert any("50k" in v.lower() for v, _ in result)

    def test_eur_no_space(self):
        result = _detect_salary("DevOps", "Ofrecemos entre 40.000€ y 50.000€", {})
        assert len(result) >= 1

    def test_salary_usd_still_works(self):
        result = _detect_salary("DevOps", "Salary: USD 120,000 - 150,000", {})
        assert len(result) >= 1

    def test_no_false_positive_on_non_salary(self):
        result = _detect_salary("DevOps", "Great benefits and PTO", {})
        assert len(result) == 0

    def test_salary_with_comma_thousands(self):
        result = _detect_salary("DevOps", "Salario entre 35.000 y 45.000 euros anuales", {})
        assert len(result) >= 1

    def test_salary_with_dot_thousands(self):
        result = _detect_salary("DevOps", "Rango salarial: €80.000 a €100.000", {})
        assert len(result) >= 1

"""Tests for dead code removal — Phase 1.

Verifies that src/dashboard/filters.py and src/dashboard/scan.py
are truly dead: nothing imports them, and removing them doesn't break
any existing import.
"""

from pathlib import Path


class TestDeadCodeVerification:
    """Verify the files exist now (pre-condition) and nothing imports them."""

    def test_dashboard_filters_module_exists_precondition(self):
        """Pre-condition: src/dashboard/filters.py exists before deletion."""
        path = Path("src/dashboard/filters.py")
        assert path.exists(), f"Pre-condition failed: {path} does not exist"

    def test_dashboard_scan_module_exists_precondition(self):
        """Pre-condition: src/dashboard/scan.py exists before deletion."""
        path = Path("src/dashboard/scan.py")
        assert path.exists(), f"Pre-condition failed: {path} does not exist"

    def test_no_live_code_imports_dashboard_filters(self):
        """No .py file under src/ (other than itself) imports from src.dashboard.filters."""
        src_root = Path("src")
        forbidden = "src.dashboard.filters"
        offenders: list[str] = []
        for py_file in src_root.rglob("*.py"):
            if py_file == Path("src/dashboard/filters.py"):
                continue
            text = py_file.read_text(encoding="utf-8")
            if forbidden in text:
                offenders.append(str(py_file))
        assert offenders == [], f"Live code still imports dead module: {offenders}"

    def test_no_live_code_imports_dashboard_scan(self):
        """No .py file under src/ (other than itself) imports from src.dashboard.scan."""
        src_root = Path("src")
        forbidden = "src.dashboard.scan"
        offenders: list[str] = []
        for py_file in src_root.rglob("*.py"):
            if py_file == Path("src/dashboard/scan.py"):
                continue
            text = py_file.read_text(encoding="utf-8")
            if forbidden in text:
                offenders.append(str(py_file))
        assert offenders == [], f"Live code still imports dead module: {offenders}"

    def test_no_test_imports_dashboard_filters(self):
        """No test file imports from src.dashboard.filters."""
        test_root = Path("tests")
        self_file = Path(__file__).resolve()
        forbidden = "src.dashboard.filters"
        offenders: list[str] = []
        for py_file in test_root.rglob("*.py"):
            if py_file.resolve() == self_file:
                continue
            # Use token-aware check: only flag actual import statements,
            # not string literals inside test assertions
            for line in py_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if ("import" in stripped or "from" in stripped) and forbidden in stripped:
                    offenders.append(str(py_file))
                    break
        assert offenders == [], f"Tests still import dead module: {offenders}"

    def test_no_test_imports_dashboard_scan(self):
        """No test file imports from src.dashboard.scan."""
        test_root = Path("tests")
        self_file = Path(__file__).resolve()
        forbidden = "src.dashboard.scan"
        offenders: list[str] = []
        for py_file in test_root.rglob("*.py"):
            if py_file.resolve() == self_file:
                continue
            for line in py_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if ("import" in stripped or "from" in stripped) and forbidden in stripped:
                    offenders.append(str(py_file))
                    break
        assert offenders == [], f"Tests still import dead module: {offenders}"

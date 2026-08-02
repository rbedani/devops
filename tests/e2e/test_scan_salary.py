"""E2E tests for SCAN salary UI bounds (SCAN-SAL-01/02/03, D5).

Demuestra:
1. Los bounds salary del UI (salary_min/salary_max) llegan como overrides
   efectivos al scan: el log del subproceso muestra
   "SCAN_SALARY_MIN override: 30000" y "SCAN_SALARY_MAX override: 45000".
   Asercion sobre el LOG DOM (#scan-log).
2. Bounds vacios = sin filtro de salary: el log muestra
   "SCAN_SALARY_MIN override: cleared (no min salary filter)" y su analogo
   para el max.
3. La advertencia D5 (min > max) se renderiza en #scan-salary-warning al
   teclear un rango invertido, sin bloquear el submit.

Nota: el SSE de progreso solo envia la ultima linea de log por tick
(0.5s), asi que para capturar el log COMPLETO se re-clicca el tab SCAN
tras finalizar el scan — el hx-get=/scan/config re-renderiza
scan_state.log_lines integro en #scan-log (mismo patron que
test_scan_keywords.py).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from playwright.sync_api import sync_playwright


def clean_database(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def seed_platforms(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO scan_platforms (name, url) VALUES (?, ?)",
        ("LinkedIn", "https://www.linkedin.com/jobs/"),
    )
    conn.commit()
    conn.close()


def _ensure_scan_tab(page, server_url: str) -> None:
    page.goto(f"{server_url}/")
    page.wait_for_timeout(1000)
    page.click("button[data-tab='scan']")
    page.wait_for_timeout(1000)
    # Open collapsible settings panel so form elements are interactable
    page.click("#settings-toggle")
    page.wait_for_timeout(500)


def _run_scan_and_wait(page, salary_min: str, salary_max: str, timeout_ms: int = 240000) -> None:
    """Fill salary bounds, enable debug, run scan, and wait until it finishes.

    The scan button is disabled while running and re-enabled by showDone()
    once the SSE emits the final event.
    """
    min_input = page.query_selector("#scan-salary-min")
    max_input = page.query_selector("#scan-salary-max")
    min_input.fill(salary_min)
    max_input.fill(salary_max)
    page.check("#scan-debug")

    page.click("#scan-btn")
    # Scan started → button disabled
    page.wait_for_function(
        "document.querySelector('.btn-scan').disabled === true",
        timeout=15000,
    )
    # Scan finished → button enabled again
    page.wait_for_function(
        "document.querySelector('.btn-scan').disabled === false",
        timeout=timeout_ms,
    )
    # Re-fetch /scan/config to render the FULL log (SSE only streams the
    # last line per tick)
    page.click("button[data-tab='scan']")
    page.wait_for_function(
        "document.getElementById('scan-log').textContent.includes('SCAN_SALARY_MIN')",
        timeout=15000,
    )


class TestScanSalaryUI:
    def test_salary_bounds_override_reaches_log_dom(self, server_url: str, db_path: Path) -> None:
        """SCAN-SAL-01: UI bounds 30000/45000 → overrides en el LOG DOM."""
        print("\n" + "=" * 60)
        print("TEST: salary_min=30000, salary_max=45000 (debug scan)")
        print(f"{'='*60}")

        clean_database(db_path)
        seed_platforms(db_path)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            _ensure_scan_tab(page, server_url)
            _run_scan_and_wait(page, "30000", "45000")

            log_text = page.text_content("#scan-log")
            assert log_text is not None, "No se encontro #scan-log en el DOM"
            print(f"  LOG DOM (tail): ...{log_text[-300:]!r}")

            assert "SCAN_SALARY_MIN override: 30000" in log_text, (
                f"El log no muestra el override de min. Log: {log_text[-500:]}"
            )
            assert "SCAN_SALARY_MAX override: 45000" in log_text, (
                f"El log no muestra el override de max. Log: {log_text[-500:]}"
            )
            print("  'SCAN_SALARY_MIN/MAX override' presente en el LOG DOM")
            print("=" * 60 + "\n")

            browser.close()

    def test_empty_salary_bounds_clear_filter(self, server_url: str, db_path: Path) -> None:
        """SCAN-SAL-02: bounds vacios = sin filtro → overrides 'cleared' en el LOG DOM."""
        print("\n" + "=" * 60)
        print("TEST: salary_min='', salary_max='' (sin filtro)")
        print(f"{'='*60}")

        clean_database(db_path)
        seed_platforms(db_path)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            _ensure_scan_tab(page, server_url)
            _run_scan_and_wait(page, "", "")

            log_text = page.text_content("#scan-log")
            assert log_text is not None, "No se encontro #scan-log en el DOM"
            print(f"  LOG DOM (tail): ...{log_text[-300:]!r}")

            assert "SCAN_SALARY_MIN override: cleared" in log_text, (
                f"El log no muestra min 'cleared'. Log: {log_text[-500:]}"
            )
            assert "SCAN_SALARY_MAX override: cleared" in log_text, (
                f"El log no muestra max 'cleared'. Log: {log_text[-500:]}"
            )
            print("  'SCAN_SALARY_MIN/MAX override: cleared' presente en el LOG DOM")
            print("=" * 60 + "\n")

            browser.close()

    def test_inverted_bounds_show_warning_but_run(self, server_url: str, db_path: Path) -> None:
        """D5: min>max muestra warning en #scan-salary-warning sin bloquear el scan."""
        print("\n" + "=" * 60)
        print("TEST: salary_min=45000 > salary_max=30000 (warning, sin bloqueo)")
        print(f"{'='*60}")

        clean_database(db_path)
        seed_platforms(db_path)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            _ensure_scan_tab(page, server_url)

            # Teclear rango invertido → warning visible
            min_input = page.query_selector("#scan-salary-min")
            max_input = page.query_selector("#scan-salary-max")
            min_input.fill("45000")
            max_input.fill("30000")
            page.wait_for_function(
                "document.getElementById('scan-salary-warning').style.display !== 'none'",
                timeout=5000,
            )
            print("  Warning D5 visible (min > max)")
            page.check("#scan-debug")
            page.click("#scan-btn")

            # El scan NO esta bloqueado: corre y termina
            page.wait_for_function(
                "document.querySelector('.btn-scan').disabled === false",
                timeout=240000,
            )
            print("  Scan completo a pesar del rango invertido (sin bloqueo)")
            print("=" * 60 + "\n")

            browser.close()

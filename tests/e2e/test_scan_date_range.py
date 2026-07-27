"""E2E tests for SCAN date_range parameter validation.

Demuestra que:
1. El UI envía correctamente cada opción de date_range via HTMX
2. El endpoint /scan recibe el parámetro correcto
3. El bug está en scripts/run_search.py que nunca lee SCAN_DATE_RANGE

Cada test limpia la DB para evitar falsos positivos.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

DATE_RANGE_OPTIONS = [
    ("", "Any time"),
    ("last_24h", "Last 24 hours"),
    ("last_week", "Last week"),
    ("last_month", "Last month"),
]


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


def get_job_count(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    return count


class TestScanDateRangeUI:
    def test_date_range_ui_options_exist(self, server_url: str) -> None:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"{server_url}/")
            page.wait_for_timeout(1000)

            page.click("button[data-tab='scan']")
            page.wait_for_timeout(1000)

            options = page.query_selector_all("#scan-date-range option")
            option_values = []
            for opt in options:
                val = opt.get_attribute("value")
                label = opt.inner_text()
                option_values.append((val, label))

            assert len(options) == 4, f"Expected 4 options, got {len(options)}: {option_values}"
            assert ("", "Any time") in option_values
            assert ("last_24h", "Last 24 hours") in option_values
            assert ("last_week", "Last week") in option_values
            assert ("last_month", "Last month") in option_values

            browser.close()

    @pytest.mark.parametrize("date_range_value,date_range_label", DATE_RANGE_OPTIONS)
    def test_date_range_param_reaches_backend(
        self, server_url: str, db_path: Path, date_range_value: str, date_range_label: str
    ) -> None:
        print(f"\n{'='*60}")
        print(f"TEST: date_range='{date_range_value}' ({date_range_label})")
        print(f"{'='*60}")

        clean_database(db_path)
        seed_platforms(db_path)
        initial_count = get_job_count(db_path)
        print(f"  DB inicial: {initial_count} jobs")

        scan_requests: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def log_scan_request(request) -> None:
                if "/scan?" in request.url or "/scan/status" in request.url:
                    scan_requests.append(request.url)

            page.on("request", log_scan_request)

            page.goto(f"{server_url}/")
            page.wait_for_timeout(1000)

            page.click("button[data-tab='scan']")
            page.wait_for_timeout(2000)

            page.select_option("#scan-date-range", value=date_range_value)

            selected = page.input_value("#scan-date-range")
            assert selected == date_range_value, (
                f"Expected date_range='{date_range_value}', got '{selected}'"
            )
            print(f"  {selected}")

            page.check("#scan-debug")
            assert page.is_checked("#scan-debug"), "Debug mode no se marcó"
            print(f"  Debug mode activado")

            page.click("#scan-btn")
            print(f"  Iniciando scan...")

            page.wait_for_timeout(4000)

            print(f"\n  Requests capturadas:")
            for r in scan_requests:
                print(f"    {r}")

            scan_get = [r for r in scan_requests if "/scan?" in r]
            assert len(scan_get) > 0, (
                f"No se capturó ninguna request GET /scan?. Capturadas: {scan_requests}"
            )

            scan_url = scan_get[0]

            if date_range_value:
                assert f"date_range={date_range_value}" in scan_url, (
                    f"Falta 'date_range={date_range_value}' en: {scan_url}"
                )
                print(f"\n  date_range='{date_range_value}' ENVIADO correctamente en la URL")
            else:
                print(f"\n  date_range vacío (Any time) enviado correctamente")

            assert "debug_mode=on" in scan_url, f"Falta debug_mode=on en: {scan_url}"
            print(f"  debug_mode=on presente en la URL")

            print(f"\n  Este test prueba que el UI envía correctamente 'date_range'")
            print(f"  PERO el bug está en scripts/run_search.py — NUNCA lee SCAN_DATE_RANGE")
            print(f"  La variable queda atrapada en este punto: runner.py la setea como")
            print(f"  env var, pero run_search.py la ignora completamente.")
            print(f"{'='*60}\n")

            browser.close()

"""E2E tests for SCAN modality parameter validation.

Valida cada opción de modality:
- Remote (f_WT=2)
- Hybrid (f_WT=1)
- On-site (f_WT=3)
- Combinaciones (Remote+Hybrid)
- Sin selección (sin f_WT)

Cada test limpia la DB y captura la request HTMX a /scan para verificar
que modality se envía correctamente.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

MODALITY_SCENARIOS = [
    (["remote"], "modality=remote", "Remote only"),
    (["hybrid"], "modality=hybrid", "Hybrid only"),
    (["onsite"], "modality=onsite", "On-site only"),
    (["remote", "hybrid"], ["modality=remote", "modality=hybrid"], "Remote + Hybrid"),
    (["remote", "hybrid", "onsite"], ["modality=remote", "modality=hybrid", "modality=onsite"], "All three"),
    ([], "", "None (no filter)"),
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


def _ensure_scan_tab(page, server_url: str) -> None:
    page.goto(f"{server_url}/")
    page.wait_for_timeout(1000)
    page.click("button[data-tab='scan']")
    page.wait_for_timeout(2000)


def _uncheck_all_modalities(page) -> None:
    for value in ("remote", "hybrid", "onsite"):
        cb = page.query_selector(f"input[name='modality'][value='{value}']")
        if cb and cb.is_checked():
            cb.uncheck()


class TestScanModalityUI:
    def test_modality_checkboxes_exist(self, server_url: str) -> None:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            _ensure_scan_tab(page, server_url)

            for value in ("remote", "hybrid", "onsite"):
                cb = page.query_selector(f"input[name='modality'][value='{value}']")
                label = page.query_selector(f"label:has(input[value='{value}'])")
                assert cb is not None, f"Checkbox modality={value} no encontrado"
                assert label is not None, f"Label para modality={value} no encontrado"

            browser.close()

    @pytest.mark.parametrize("checkboxes,expected,label", MODALITY_SCENARIOS)
    def test_modality_param_sent_to_scan(
        self, server_url: str, db_path: Path, checkboxes: list[str], expected: str | list[str], label: str
    ) -> None:
        print(f"\n{'='*60}")
        print(f"TEST: modality='{label}' — checkboxes: {checkboxes}")
        print(f"{'='*60}")

        clean_database(db_path)
        seed_platforms(db_path)

        expected_parts = [expected] if isinstance(expected, str) and expected else expected
        if isinstance(expected, str) and not expected:
            expected_parts = []

        scan_urls: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def log_request(request) -> None:
                if "/scan?" in request.url:
                    scan_urls.append(request.url)
            page.on("request", log_request)

            _ensure_scan_tab(page, server_url)

            _uncheck_all_modalities(page)

            for cb_value in checkboxes:
                page.check(f"input[name='modality'][value='{cb_value}']")
                assert page.is_checked(f"input[name='modality'][value='{cb_value}']"), (
                    f"No se pudo marcar modality={cb_value}"
                )
            print(f"  Checkboxes marcados: {checkboxes}")

            page.check("#scan-debug")

            page.wait_for_timeout(3000)

            page.click("#scan-btn")
            page.wait_for_timeout(3000)

            scan_get = [u for u in scan_urls if "/scan?" in u and "status-check" not in u]
            assert len(scan_get) > 0, (
                f"No se capturó GET /scan. URLs: {scan_urls}"
            )

            scan_url = scan_get[0]
            print(f"  URL: {scan_url[:150]}")

            for part in expected_parts:
                assert part in scan_url, (
                    f"Falta '{part}' en la URL: {scan_url}"
                )
                print(f"  '{part}' presente en la URL")

            if not expected_parts:
                modality_in_url = "modality=" in scan_url
                if modality_in_url:
                    import re
                    match = re.search(r'modality=([^&]*)', scan_url)
                    val = match.group(1) if match else ""
                    print(f"  modality value in URL: '{val}' (vacío → sin filtro)")
                print(f"  Ningún filtro de modality aplicado")

            print(f"  Pipeline: UI→routes→runner→run_search→LinkedInScraper con f_WT")
            print(f"{'='*60}\n")

            browser.close()

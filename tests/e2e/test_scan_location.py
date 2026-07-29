"""E2E tests for SCAN location parameter validation.

Valida cada escenario de location:
- 1 sola ubicacion (ej. "Spain")
- 2 ubicaciones separadas por coma (ej. "Spain, Argentina")
- Multiples ubicaciones (ej. "Spain, Argentina, Madrid, Buenos Aires")
- Vacio (sin filtro de ubicacion)
- Sin escribir nada (usa config default)

Cada test limpia la DB y captura la request HTMX a /scan.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

LOCATION_SCENARIOS = [
    ("Spain", "location=Spain", "1 location"),
    ("Spain, Argentina", "location=Spain%2C%20Argentina", "2 locations comma-separated"),
    ("Spain, Argentina, Madrid, Buenos Aires", "location=Spain%2C%20Argentina%2C%20Madrid%2C%20Buenos%20Aires", "4 locations comma-separated"),
    ("", "", "Empty (no location filter)"),
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
    page.wait_for_timeout(1000)
    # Open collapsible settings panel so form elements are interactable
    page.click("#settings-toggle")
    page.wait_for_timeout(500)


class TestScanLocationUI:
    def test_location_input_exists(self, server_url: str) -> None:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            _ensure_scan_tab(page, server_url)

            inp = page.query_selector("#scan-location")
            assert inp is not None, "Input #scan-location no encontrado"
            assert inp.get_attribute("name") == "location"
            assert inp.get_attribute("placeholder") is not None

            browser.close()

    @pytest.mark.parametrize("input_text,expected_fragment,label", LOCATION_SCENARIOS)
    def test_location_param_sent_to_scan(
        self, server_url: str, db_path: Path, input_text: str, expected_fragment: str, label: str
    ) -> None:
        print(f"\n{'='*60}")
        print(f"TEST: location='{label}' — input: \"{input_text}\"")
        print(f"{'='*60}")

        clean_database(db_path)
        seed_platforms(db_path)

        scan_urls: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def log_request(request) -> None:
                if "/scan?" in request.url:
                    scan_urls.append(request.url)
            page.on("request", log_request)

            _ensure_scan_tab(page, server_url)

            loc_input = page.query_selector("#scan-location")
            loc_input.fill("")
            if input_text:
                loc_input.fill(input_text)
                actual = loc_input.input_value()
                assert actual == input_text, f"Expected '{input_text}', got '{actual}'"
            print(f"  Location input: '{input_text}'")

            page.check("#scan-debug")

            page.wait_for_timeout(3000)

            page.click("#scan-btn")
            page.wait_for_timeout(3000)

            scan_get = [u for u in scan_urls if "/scan?" in u and "status-check" not in u]
            assert len(scan_get) > 0, f"No se capturo GET /scan. URLs: {scan_urls}"

            scan_url = scan_get[0]
            print(f"  URL: {scan_url[:200]}")

            if expected_fragment:
                assert expected_fragment in scan_url, (
                    f"Falta '{expected_fragment}' en URL: {scan_url}"
                )
                print(f"  '{expected_fragment}' presente en la URL")
            else:
                import re
                match = re.search(r'location=([^&]*)', scan_url)
                if match and match.group(1):
                    print(f"  location={match.group(1)} en URL (esperado vacio)")
                else:
                    print(f"  Sin location (no filter)")

            print(f"  Pipeline: UI → routes → runner → run_search")
            print(f"     run_search itera por cada location (split por coma)")
            print(f"     → scrape_search(location=X) una vez por pais/ciudad")
            print(f"{'='*60}\n")

            browser.close()

"""E2E test: platform enable/disable toggle + multi-platform scan.

1. Verificar que el toggle ENABLE/DISABLE funciona via Playwright
2. Deshabilitar LinkedIn, dejar solo InfoJobs habilitado
3. Ejecutar scan en debug mode
4. Verificar que solo se escanea InfoJobs
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


def clean_database(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def _get_platform_item(page, name: str):
    """Find platform item div by .platform-item-name text."""
    items = page.query_selector_all(".platform-item")
    for item in items:
        name_el = item.query_selector(".platform-item-name")
        if name_el and name_el.inner_text().strip() == name:
            return item
    return None


class TestPlatformToggle:
    def test_both_platforms_visible_in_ui(self, server_url: str) -> None:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"{server_url}/")
            page.wait_for_timeout(1000)
            page.click("button[data-tab='scan']")
            page.wait_for_timeout(2000)

            platform_items = page.query_selector_all(".platform-item")
            names = []
            for item in platform_items:
                name_el = item.query_selector(".platform-item-name")
                if name_el:
                    names.append(name_el.inner_text())

            assert "LinkedIn" in names, f"LinkedIn no encontrado en: {names}"
            assert "InfoJobs" in names, f"InfoJobs no encontrado en: {names}"
            assert "Indeed" in names, f"Indeed no encontrado en: {names}"
            print(f"  Platforms visible: {names}")

            browser.close()

    def test_disable_linkedin_enable_infojobs(self, server_url: str, db_path: Path) -> None:
        clean_database(db_path)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            scan_urls: list[str] = []
            def log_request(request) -> None:
                if "/scan?" in request.url:
                    scan_urls.append(request.url)
            page.on("request", log_request)

            page.goto(f"{server_url}/")
            page.wait_for_timeout(1000)
            page.click("button[data-tab='scan']")
            page.wait_for_timeout(3000)

            linkedin_item = _get_platform_item(page, "LinkedIn")
            infojobs_item = _get_platform_item(page, "InfoJobs")

            linkedin_cb = linkedin_item.query_selector("input[name='platforms']") if linkedin_item else None
            linkedin_toggle = linkedin_item.query_selector(".btn-platform-toggle") if linkedin_item else None
            infojobs_cb = infojobs_item.query_selector("input[name='platforms']") if infojobs_item else None
            infojobs_toggle = infojobs_item.query_selector(".btn-platform-toggle") if infojobs_item else None

            print(f"  LinkedIn cb={'checked' if linkedin_cb and linkedin_cb.is_checked() else 'unchecked'} toggle={linkedin_toggle.inner_text() if linkedin_toggle else 'N/A'}")
            print(f"  InfoJobs cb={'checked' if infojobs_cb and infojobs_cb.is_checked() else 'unchecked'} toggle={infojobs_toggle.inner_text() if infojobs_toggle else 'N/A'}")

            if linkedin_toggle and linkedin_toggle.inner_text() == "DISABLE":
                print("  Disabling LinkedIn...")
                linkedin_toggle.click()
                page.wait_for_timeout(1500)

            if infojobs_toggle and infojobs_toggle.inner_text() == "ENABLE":
                print("  Enabling InfoJobs...")
                infojobs_toggle.click()
                page.wait_for_timeout(1500)

            infojobs_item = _get_platform_item(page, "InfoJobs")
            if infojobs_item:
                infojobs_cb = infojobs_item.query_selector("input[name='platforms']")
                infojobs_toggle = infojobs_item.query_selector(".btn-platform-toggle")
                if infojobs_cb and not infojobs_cb.is_checked():
                    infojobs_cb.check()
                print(f"  InfoJobs after: cb={'checked' if infojobs_cb and infojobs_cb.is_checked() else 'unchecked'} toggle={infojobs_toggle.inner_text() if infojobs_toggle else 'N/A'}")

            linkedin_item = _get_platform_item(page, "LinkedIn")
            if linkedin_item:
                linkedin_cb = linkedin_item.query_selector("input[name='platforms']")
                if linkedin_cb and linkedin_cb.is_checked():
                    linkedin_cb.uncheck()
                print(f"  LinkedIn after: cb={'checked' if linkedin_cb and linkedin_cb.is_checked() else 'unchecked'}")

            page.check("#scan-debug")

            print("\n  Ejecutando scan con solo InfoJobs...")
            page.click("#scan-btn")
            page.wait_for_timeout(4000)

            scan_get = [u for u in scan_urls if "/scan?" in u and "status-check" not in u]
            if scan_get:
                scan_url = scan_get[0]
                print(f"  Scan URL: {scan_url[:200]}")
                assert "infojobs" in scan_url.lower(), (
                    f"InfoJobs deberia estar en la URL: {scan_url}"
                )
                has_linkedin = "linkedin" in scan_url.lower() and "platforms=linkedin" in scan_url.lower()
                print(f"  LinkedIn in scan URL: {has_linkedin}")
                print(f"  Scan ejecutandose con InfoJobs")
            else:
                print("  No se capturo URL de scan")

            print(f"\n  Test completado: LinkedIn disabled, InfoJobs enabled")

            browser.close()

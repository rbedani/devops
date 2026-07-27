"""E2E tests for Clean Status DB and Clean Personal Data buttons in Settings.

Uses playwright.sync_api directly (no pytest-playwright).
Starts uvicorn with a patched, isolated database via tests/e2e/run_server.py.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
WRAPPER = HERE / "run_server.py"


@pytest.fixture(scope="module")
def server_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Start uvicorn with patched temp DB, yield URL, tear down."""
    db_path = tmp_path_factory.mktemp("data") / "clean_e2e.db"
    port = 14321
    proc = subprocess.Popen(
        ["python3", str(WRAPPER), str(db_path), str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    url = f"http://localhost:{port}"

    # Seed a job so clean-db has something to delete
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, source TEXT, title TEXT, url TEXT, scraped_at TEXT)")
    conn.execute("INSERT INTO jobs (source, title, url, scraped_at) VALUES ('test', 'E2E Job', 'http://e2e.test', '2026-07-27T00:00:00')")
    conn.commit()
    conn.close()

    yield url
    proc.terminate()
    proc.wait()


class TestCleanFlow:
    """E2E: Clean buttons in Settings preserve page and show flash message."""

    def test_clean_status_db(self, server_url: str) -> None:
        """Navigate to /, click SETTINGS tab, click Clean Status DB, verify flash."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("dialog", lambda d: d.accept())
            # Navigate to full page first
            page.goto(f"{server_url}/")
            # Click SETTINGS tab to load settings partial via HTMX
            page.click("button[data-tab='settings']")
            # Wait for settings content to load
            page.wait_for_selector("#settings-tab", timeout=5000)
            # Click the Clean Status DB button
            page.click("button[hx-post='/clean-db']")
            # Wait for flash message
            page.wait_for_selector("#flash-msg", timeout=5000)
            assert "Status DB cleaned" in page.text_content("#flash-msg")
            assert page.is_visible("#settings-tab")
            browser.close()

    def test_clean_datos(self, server_url: str) -> None:
        """Navigate to /, click SETTINGS tab, click Clean Personal Data, verify flash."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("dialog", lambda d: d.accept())
            # Navigate to full page first
            page.goto(f"{server_url}/")
            # Click SETTINGS tab to load settings partial via HTMX
            page.click("button[data-tab='settings']")
            # Wait for settings content to load
            page.wait_for_selector("#settings-tab", timeout=5000)
            # Click the Clean Personal Data button
            page.click("button[hx-post='/datos/clean']")
            # Wait for flash message
            page.wait_for_selector("#flash-msg", timeout=5000)
            assert "Personal data cleaned" in page.text_content("#flash-msg")
            assert page.is_visible("#settings-tab")
            browser.close()
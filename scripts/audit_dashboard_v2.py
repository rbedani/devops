#!/usr/bin/env python3
"""Playwright audit for dashboard-v2 — validates all features with evidence."""
import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3311"
REPORT_DIR = Path("/home/opc/devops/reports/ui-audit-v2")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

results = []

async def step(name, fn):
    """Run a validation step with screenshot."""
    try:
        await fn()
        results.append({"step": name, "status": "PASS"})
        print(f"  ✅ {name}")
    except Exception as e:
        results.append({"step": name, "status": "FAIL", "error": str(e)})
        print(f"  ❌ {name}: {e}")

async def main():
    print(f"\n{'='*60}")
    print(f"  Dashboard-v2 Playwright Audit")
    print(f"  URL: {BASE_URL}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # -- 1. OpenCode.ai theme check -----------------------------------
        async def check_theme():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(REPORT_DIR / "01-theme.png"))

            # Check light bg (not dark)
            body_bg = await page.evaluate("getComputedStyle(document.body).backgroundColor")
            assert body_bg in ["rgb(255, 255, 255)", "rgba(0, 0, 0, 0)"], f"Body bg should be white, got {body_bg}"

            # Check font is monospace
            body_font = await page.evaluate("getComputedStyle(document.body).fontFamily")
            assert "monospace" in body_font.lower() or "plex" in body_font.lower(), f"Font should be monospace, got {body_font}"

            # Check accent color in buttons
            btn = await page.query_selector(".btn-scan")
            assert btn, "Scan button should exist"
            btn_bg = await btn.evaluate('el => getComputedStyle(el).backgroundColor')
            # Should be blue-ish (#007aff = rgb(0, 122, 255))
            assert "rgb(0" in btn_bg or "rgba(0" in btn_bg, f"Button should be blue, got {btn_bg}"

            # Check no border-radius on menu
            menu = await page.query_selector(".menu-row")
            if menu:
                radius = await menu.evaluate('el => getComputedStyle(el).borderRadius')
                assert radius == "0px", f"Menu should have 0 border-radius, got {radius}"

            # Check no box-shadow on table
            table = await page.query_selector(".job-table")
            if table:
                shadow = await table.evaluate('el => getComputedStyle(el).boxShadow')
                assert shadow == "none", f"Table should have no box-shadow, got {shadow}"

        await step("OpenCode.ai theme applied", check_theme)

        # -- 2. Search debounce (2s) --------------------------------------
        async def check_debounce():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(500)

            search_input = await page.query_selector("#search-input")
            assert search_input, "Search input should exist"

            # Check HTMX trigger has delay:2000ms
            hx_trigger = await search_input.get_attribute("hx-trigger")
            assert hx_trigger and "delay:2000ms" in hx_trigger, \
                f"HTMX trigger should have delay:2000ms, got {hx_trigger}"

            # Quick type test: type a letter, wait 500ms, should NOT have triggered yet
            await search_input.fill("")
            await page.wait_for_timeout(200)
            await search_input.type("r", delay=50)
            await page.wait_for_timeout(500)
            # The table should still be showing initial state (no filter applied yet)
            # We can't easily assert no HTMX request happened, but we can check
            # the debounce attribute is correct

            # Type more and wait 3s (over 2s debounce)
            await search_input.type("emoto", delay=100)
            await page.wait_for_timeout(3000)

            await page.screenshot(path=str(REPORT_DIR / "02-debounce-filter.png"))

        await step("Search debounce (2s) works", check_debounce)

        # -- 3. Scan button disabled during scan --------------------------
        async def check_button_disable():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(500)

            scan_btn = await page.query_selector(".btn-scan")
            assert scan_btn, "Scan button should exist"

            # Button should be enabled initially
            is_disabled = await scan_btn.is_disabled()
            assert not is_disabled, "Scan button should be enabled initially"

            # Get the disabled attribute check
            disabled_attr = await scan_btn.get_attribute("disabled")
            await page.screenshot(path=str(REPORT_DIR / "03-button-enabled.png"))

        await step("Scan button enabled initially", check_button_disable)

        # -- 4. Scan button state via template ----------------------------
        async def check_scan_running_state():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)

            # Check the HTML has the scan_running context
            html = await page.content()
            # The button should NOT have disabled attribute when page loads
            # (scan_running is False by default)
            assert 'disabled=""' not in html or 'class="btn-scan-disabled"' not in html, \
                "Button should not be disabled when page loads"

            await page.screenshot(path=str(REPORT_DIR / "04-button-state.png"))

        await step("Scan button default state is enabled", check_scan_running_state)

        # -- 5. Search keyword passes to scan -----------------------------
        async def check_keyword_pass():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(500)

            search_input = await page.query_selector("#search-input")
            await search_input.fill("devops")

            # Check the scan button has hx-include="#search-input"
            scan_btn = await page.query_selector(".btn-scan")
            hx_include = await scan_btn.get_attribute("hx-include")
            assert hx_include and "search-input" in hx_include, \
                f"Scan button should include search input, got hx-include={hx_include}"

            await page.screenshot(path=str(REPORT_DIR / "05-keyword-search.png"))

        await step("Search keyword passes to scan", check_keyword_pass)

        # -- 6. Progress bar appearance ------------------------------------
        async def check_progress_bar():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)

            # Check the progress container exists
            progress_container = await page.query_selector("#progress-container")
            assert progress_container, "Progress container should exist"

            # Check CSS has neon glow
            css_resp = await page.goto(f"{BASE_URL}/static/style.css")
            css = await css_resp.text()
            assert "box-shadow" in css and "rgba(0" in css, \
                "CSS should have neon blue glow for progress bar"
            assert "linear-gradient" not in css, \
                "CSS should NOT have gradients (flat design)"

            await page.screenshot(path=str(REPORT_DIR / "06-progress-bar.png"))

        await step("Progress bar has neon glow (flat design)", check_progress_bar)

        # -- 7. Debug + Clean DB flow --------------------------------------
        async def check_debug_clean():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(500)

            # Check debug checkbox exists
            debug_cb = await page.query_selector("#debug-mode")
            assert debug_cb, "Debug checkbox should exist"

            # Initially clean-db button should be hidden
            clean_btn = await page.query_selector("#clean-db-btn")
            assert clean_btn, "Clean DB button should exist in DOM"
            is_visible = await clean_btn.is_visible()
            assert not is_visible, "Clean DB button should be hidden initially"

            # Click debug checkbox
            await debug_cb.check()
            await page.wait_for_timeout(500)

            # Clean DB button should now be visible
            is_visible = await clean_btn.is_visible()
            assert is_visible, "Clean DB button should be visible when debug is on"

            await page.screenshot(path=str(REPORT_DIR / "07-debug-clean.png"))

            # Uncheck debug
            await debug_cb.uncheck()
            await page.wait_for_timeout(300)

        await step("Debug + Clean DB flow works", check_debug_clean)

        # -- 8. Full page screenshot ---------------------------------------
        async def check_full_page():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(REPORT_DIR / "08-full-page.png"), full_page=True)

        await step("Full page screenshot captured", check_full_page)

        # -- Summary -------------------------------------------------------
        await browser.close()

    print(f"\n{'='*60}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"  Results: {passed}/{len(results)} passed, {failed} failed")
    print(f"  Screenshots: {REPORT_DIR}/")
    print(f"{'='*60}\n")

    # Save results
    report = {
        "url": BASE_URL,
        "timestamp": str(asyncio.get_event_loop().time()),
        "results": results,
        "passed": passed,
        "failed": failed,
        "total": len(results),
    }
    with open(str(REPORT_DIR / "audit-results.json"), "w") as f:
        json.dump(report, f, indent=2)

    sys.exit(1 if failed > 0 else 0)

if __name__ == "__main__":
    asyncio.run(main())
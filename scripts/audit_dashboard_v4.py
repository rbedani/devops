#!/usr/bin/env python3
"""Playwright audit for dashboard-v4 — theme toggle, multi-platform, footer stats."""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3311"
REPORT_DIR = Path("/home/opc/devops/reports/ui-audit-v4")
REPORT_DIR.mkdir(parents=True, exist_ok=True)
results = []

async def step(name, fn):
    try:
        await fn()
        results.append({"step": name, "status": "PASS"})
        print(f"  \u2705 {name}")
    except Exception as e:
        results.append({"step": name, "status": "FAIL", "error": str(e)})
        print(f"  \u274c {name}: {e}")

async def main():
    print(f"\n{'='*60}")
    print(f"  Dashboard-v4 Playwright Audit")
    print(f"  URL: {BASE_URL}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)

        # ── 1. Theme toggle on the right side ──────────────────────────
        async def check_theme_group_styles():
            group = await page.query_selector(".theme-switch-group")
            assert group, ".theme-switch-group should exist"
            # Check via stylesheet rule (computed value may resolve to pixels)
            has_rule = await group.evaluate("""el => {
                for (const sheet of document.styleSheets) {
                    try {
                        for (const rule of sheet.cssRules) {
                            if (rule.selectorText === '.theme-switch-group' &&
                                rule.style.marginLeft === 'auto') return true;
                        }
                    } catch(e) {}
                }
                return false;
            }""")
            assert has_rule, ".theme-switch-group should have margin-left: auto in CSS"
        await step("1a. .theme-switch-group has margin-left: auto", check_theme_group_styles)

        async def check_theme_icons():
            content = await page.content()
            assert "\u2600\ufe0f" in content, "Sun icon (\u2600\ufe0f) should be present"
            assert "\U0001f319" in content, "Moon icon (\U0001f319) should be present"
        await step("1b. Sun and Moon icons present", check_theme_icons)

        async def check_toggle_dark_light():
            await page.evaluate("localStorage.removeItem('dashboard-theme')")
            await page.reload(wait_until="networkidle")
            theme = await page.evaluate("document.documentElement.getAttribute('data-theme')")
            assert theme == "dark", f"Default should be dark, got {theme}"

            await page.evaluate("""() => {
                document.getElementById('theme-toggle').checked = true;
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem('dashboard-theme', 'light');
            }""")
            await page.wait_for_timeout(300)
            theme = await page.evaluate("document.documentElement.getAttribute('data-theme')")
            assert theme == "light", f"Should be light after toggle, got {theme}"
            stored = await page.evaluate("localStorage.getItem('dashboard-theme')")
            assert stored == "light", f"localStorage should be 'light', got {stored}"

            await page.evaluate("""() => {
                document.getElementById('theme-toggle').checked = false;
                document.documentElement.setAttribute('data-theme', 'dark');
                localStorage.setItem('dashboard-theme', 'dark');
            }""")
            await page.wait_for_timeout(300)
            theme = await page.evaluate("document.documentElement.getAttribute('data-theme')")
            assert theme == "dark", f"Should be dark after toggle back, got {theme}"
            await page.screenshot(path=str(REPORT_DIR / "01-theme-dark.png"))
        await step("1c. Toggle dark/light works", check_toggle_dark_light)

        # ── 2. Platform multi-select combo ────────────────────────────
        async def check_platform_select():
            sel = await page.query_selector("#platform-select")
            assert sel, "#platform-select should exist"
            multiple = await sel.get_attribute("multiple")
            assert multiple is not None, "#platform-select should have 'multiple' attribute"
            opts = await sel.evaluate("el => Array.from(el.options).map(o => o.value)")
            assert "linkedin" in opts, f"linkedin option missing, got {opts}"
        await step("2a. #platform-select exists with multiple + linkedin option", check_platform_select)

        async def check_scan_include():
            btn = await page.query_selector("#scan-btn")
            assert btn, "#scan-btn should exist"
            include = await btn.get_attribute("hx-include")
            assert include is not None, "SCAN button should have hx-include"
            assert "#platform-select" in include, f"hx-include should reference #platform-select, got '{include}'"
        await step("2b. SCAN button includes #platform-select in hx-include", check_scan_include)

        # ── 3. Multi-platform scan ────────────────────────────────────
        async def check_scan_sends_platforms():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            # Server may disable button if scan_running; force-enable for test
            await page.evaluate("document.querySelector('#scan-btn').disabled = false")
            async with page.expect_response(lambda r: "/scan" in r.url and r.request.method == "GET") as resp_info:
                await page.evaluate("document.querySelector('#scan-btn').click()")
            resp = await resp_info.value
            url = resp.request.url
            assert "platforms" in url, f"Scan request should include 'platforms' param, url: {url}"
        await step("3a. Scan button sends platforms param", check_scan_sends_platforms)

        async def check_progress_bar():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.evaluate("document.querySelector('#scan-btn').disabled = false")
            async with page.expect_response(lambda r: "/scan" in r.url and r.request.method == "GET") as resp_info:
                await page.evaluate("document.querySelector('#scan-btn').click()")
            await resp_info.value
            await page.wait_for_timeout(1000)
            progress = await page.query_selector("#progress-container")
            inner = await progress.inner_html() if progress else ""
            assert progress and inner.strip(), "progress-container should have content after scan"
            await page.screenshot(path=str(REPORT_DIR / "03-scan-progress.png"))
        await step("3b. Progress bar appears after scan", check_progress_bar)

        # ── 4. Footer stats ───────────────────────────────────────────
        async def check_footer_job_count():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            footer = await page.query_selector(".dashboard-footer")
            assert footer, ".dashboard-footer should exist"
            text = await footer.inner_text()
            assert "jobs" in text.lower(), f"Footer should contain job count, got: {text}"
            assert "Job Dashboard release v1.0" in text, f"Footer missing version string, got: {text}"
            assert "2026-07-25" in text, f"Footer missing date, got: {text}"
            await page.screenshot(path=str(REPORT_DIR / "04-footer-stats.png"))
        await step("4. Footer shows job count and version", check_footer_job_count)

        # ── 5. Full page screenshot ───────────────────────────────────
        async def check_full_page():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(REPORT_DIR / "05-full-page.png"), full_page=True)
        await step("5. Full page screenshot", check_full_page)

        await browser.close()

    print(f"\n{'='*60}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"  Results: {passed}/{len(results)} passed, {failed} failed")
    print(f"  Screenshots: {REPORT_DIR}/")
    print(f"{'='*60}\n")

    report = {
        "url": BASE_URL,
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
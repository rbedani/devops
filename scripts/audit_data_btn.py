#!/usr/bin/env python3
"""Playwright audit: DATA button toggle — table ↔ form view."""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3311"
OUT = Path("/home/opc/devops/reports/audit-data-btn")
OUT.mkdir(parents=True, exist_ok=True)
results = []

async def step(name, fn):
    try:
        await fn()
        results.append({"step": name, "status": "PASS"})
        print(f"  ✅ {name}")
    except Exception as e:
        results.append({"step": name, "status": "FAIL", "error": str(e)})
        print(f"  ❌ {name}: {e}")

async def main():
    print(f"\n{'='*60}")
    print(f"  DATA Button — Playwright Audit")
    print(f"  URL: {BASE_URL}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # 1. Load dashboard
        async def load_dashboard():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(OUT / "01-initial-table.png"))
            # Verify default view: table visible, no form
            table = await page.query_selector("#table-container")
            assert table, "Table container should be visible on load"
            form = await page.query_selector(".data-form")
            assert not form, "Data form should NOT be visible on load"
        await step("Default view shows table, no form", load_dashboard)

        # 2. DATA button exists and says DATA
        async def data_btn_initial():
            btn = await page.query_selector("#data-btn")
            assert btn, "DATA button (#data-btn) must exist in DOM"
            text = await btn.text_content()
            assert text.strip() == "DATA", f"Button text should be 'DATA', got '{text.strip()}'"
            # Check it's in the header-right area
            parent = await btn.evaluate("el => el.closest('.header-right') !== null")
            assert parent, "DATA button must be inside .header-right"
            await page.screenshot(path=str(OUT / "02-data-btn-initial.png"))
        await step("DATA button exists in header-right, says DATA", data_btn_initial)

        # 3. Click DATA → shows form, button says TABLE
        async def click_data_shows_form():
            btn = await page.query_selector("#data-btn")
            await btn.click()
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(OUT / "03-after-data-click.png"))
            # Form should now be visible
            form = await page.query_selector(".data-form")
            assert form, "Data form (.data-form) should appear after clicking DATA"
            # Table should NOT be visible (main-content swapped)
            form_title = await page.query_selector(".data-form-title")
            assert form_title, "Form should have a title (.data-form-title)"
            title_text = await form_title.text_content()
            assert title_text, "Form title should have text"
            # Button should now say TABLE
            text = await btn.text_content()
            assert text.strip() == "TABLE", f"Button should say 'TABLE', got '{text.strip()}'"
            # Button should have active class
            cls = await btn.get_attribute("class")
            assert cls and "btn-data-active" in cls, "Button should have btn-data-active class"
        await step("Click DATA → form visible, button says TABLE, active class", click_data_shows_form)

        # 4. Form fields exist
        async def form_fields_present():
            fields = ["full-name", "email", "phone", "cv-path", "cover-letter"]
            for fid in fields:
                el = await page.query_selector(f"#{fid}")
                assert el, f"Form field #{fid} should exist"
            save_btn = await page.query_selector(".form-actions .btn-primary")
            assert save_btn, "SAVE button should exist"
            test_btn = await page.query_selector(".form-actions .btn-toggle")
            assert test_btn, "TEST button should exist"
            await page.screenshot(path=str(OUT / "04-form-fields.png"))
        await step("Form has all fields + SAVE/TEST buttons", form_fields_present)

        # 5. Click TABLE → back to table, button says DATA
        async def click_table_returns():
            btn = await page.query_selector("#data-btn")
            await btn.click()
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(OUT / "05-back-to-table.png"))
            # Table should be back
            table = await page.query_selector("#table-container")
            assert table, "Table should reappear after clicking TABLE"
            # Form should be gone
            form = await page.query_selector(".data-form")
            assert not form, "Data form should be gone after clicking TABLE"
            # Button should say DATA again
            text = await btn.text_content()
            assert text.strip() == "DATA", f"Button should say 'DATA', got '{text.strip()}'"
            # Active class should be removed
            cls = await btn.get_attribute("class")
            assert not cls or "btn-data-active" not in cls, "Active class should be removed"
        await step("Click TABLE → table back, button says DATA, no active class", click_table_returns)

        # 6. Toggle twice more (DATA → TABLE → DATA) to confirm stability
        async def toggle_cycle_stability():
            btn = await page.query_selector("#data-btn")
            # DATA → form
            await btn.click()
            await page.wait_for_timeout(300)
            form = await page.query_selector(".data-form")
            assert form, "Form should appear on second toggle"
            # TABLE → table
            await btn.click()
            await page.wait_for_timeout(300)
            table = await page.query_selector("#table-container")
            assert table, "Table should reappear on third toggle"
            await page.screenshot(path=str(OUT / "06-toggle-cycle.png"))
        await step("Two full toggle cycles work (DATA→TABLE→DATA)", toggle_cycle_stability)

        # 7. Full page screenshot
        async def full_page():
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(OUT / "07-full-page.png"), full_page=True)
        await step("Full page screenshot captured", full_page)

        await browser.close()

    print(f"\n{'='*60}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"  Results: {passed}/{len(results)} passed, {failed} failed")
    print(f"  Screenshots: {OUT}/")
    print(f"{'='*60}\n")

    report = {"url": BASE_URL, "results": results, "passed": passed, "failed": failed, "total": len(results)}
    with open(str(OUT / "audit-results.json"), "w") as f:
        json.dump(report, f, indent=2)
    sys.exit(1 if failed > 0 else 0)

if __name__ == "__main__":
    asyncio.run(main())
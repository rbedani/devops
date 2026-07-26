#!/usr/bin/env python3
"""
Playwright audit script for the flat-design dashboard refactor.

Captures screenshots of the debug mode flow:
  1. Initial dashboard
  2. Debug ON (CLEAN DB visible)
  3. After CLEAN DB (empty table)
  4. Debug OFF

Usage:
    python scripts/audit_flat.py
    DASHBOARD_URL=http://localhost:3311 python scripts/audit_flat.py

Requires:
    playwright library installed (pip install playwright)
    Chromium browser binaries (playwright install chromium)
    Dashboard running at the configured URL

Exit code: 0 on success, 1 on failure.
"""

import os
import sys
from pathlib import Path

REPORTS_DIR = Path("reports/ui-audit")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3311")


def main() -> int:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeoutError

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeoutError
    except ImportError:
        print("[FAIL] playwright library not installed. Run: pip install playwright")
        return 1

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    screenshots_taken = []
    steps_completed = 0

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            # Step 1: Open the dashboard
            try:
                page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=15000)
            except Exception as exc:
                print(f"[FAIL] Cannot reach {DASHBOARD_URL} — is the server running?")
                print(f"       {exc}")
                return 1

            page.wait_for_timeout(1000)  # Let CSS settle
            page.screenshot(path=str(REPORTS_DIR / "01-initial.png"))
            screenshots_taken.append("01-initial.png")
            steps_completed += 1
            print("[OK] 01-initial.png — dashboard loaded")

            # Step 2: Check debug checkbox is present and click it
            debug_checkbox = page.locator(".debug-checkbox")
            if debug_checkbox.count() == 0:
                print("[FAIL] Debug checkbox not found — expected .debug-checkbox")
                return 1

            debug_checkbox.click()
            page.wait_for_timeout(800)
            page.screenshot(path=str(REPORTS_DIR / "02-debug-on.png"))
            screenshots_taken.append("02-debug-on.png")
            steps_completed += 1
            print("[OK] 02-debug-on.png — debug checkbox clicked, CLEAN DB should be visible")

            # Step 3: Click CLEAN DB button
            clean_btn = page.locator(".btn-clean")
            if clean_btn.count() == 0:
                print("[FAIL] CLEAN DB button (.btn-clean) not found after enabling debug")
                return 1

            clean_btn.click()
            page.wait_for_timeout(1500)  # Wait for table refresh
            page.screenshot(path=str(REPORTS_DIR / "03-after-clean.png"))
            screenshots_taken.append("03-after-clean.png")
            steps_completed += 1
            print("[OK] 03-after-clean.png — CLEAN DB clicked, table should be empty")

            # Step 4: Click debug checkbox again to turn it off
            debug_checkbox.click()
            page.wait_for_timeout(800)
            page.screenshot(path=str(REPORTS_DIR / "04-debug-off.png"))
            screenshots_taken.append("04-debug-off.png")
            steps_completed += 1
            print("[OK] 04-debug-off.png — debug mode disabled")

            # Summary
            print()
            print("=" * 60)
            print("  Playwright Audit — Flat Design Dashboard")
            print("=" * 60)
            print(f"  URL:          {DASHBOARD_URL}")
            print(f"  Output dir:   {REPORTS_DIR.resolve()}")
            print(f"  Steps passed: {steps_completed}/4")
            print(f"  Screenshots:")
            for s in screenshots_taken:
                size = (REPORTS_DIR / s).stat().st_size
                print(f"    {s:30s} {size:>8,d} bytes")
            print(f"  Status:       {'✅ ALL PASSED' if steps_completed == 4 else '❌ PARTIAL'}")
            print("=" * 60)

            context.close()
            browser.close()

    except PwTimeoutError:
        print(f"[FAIL] Timeout while interacting with {DASHBOARD_URL}")
        return 1
    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}")
        return 1

    return 0 if steps_completed == 4 else 1


if __name__ == "__main__":
    sys.exit(main())

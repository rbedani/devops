"""Playwright-based auto-apply runner for job applications."""

from __future__ import annotations

from playwright.async_api import async_playwright


class AutoApply:
    """Playwright-based auto-apply for a single job URL.

    Opens the job URL, fills profile fields and attaches CV,
    submits the application, and returns a classified status value.
    """

    def __init__(
        self,
        profile_fields: list[dict[str, str]],
        cv_path: str | None = None,
    ) -> None:
        """Initialize with user profile fields and optional CV path.

        Args:
            profile_fields: List of dicts with 'name', 'field_type', 'value'.
            cv_path: Absolute path to the CV file, or None.
        """
        self.profile_fields = profile_fields
        self.cv_path = cv_path

    async def apply(self, url: str) -> str:
        """Run the auto-apply for one job URL.

        Opens a headless browser, navigates to the job URL,
        fills form fields from profile data, attaches CV,
        and submits. Returns the classified outcome status.

        Args:
            url: The job listing URL to apply on.

        Returns:
            One of: 'postulado', 'needs-registration',
            'auto-apply-failed-unavailable', 'general-error'.
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                try:
                    await page.goto(url, timeout=30000)
                except Exception:
                    await browser.close()
                    return "auto-apply-failed-unavailable"

                # Check if submit button exists (basic form detection)
                submit_btn = await page.query_selector(
                    "button[type='submit'], input[type='submit'], "
                    "button:has-text('Apply'), button:has-text('Postularme'), "
                    "button:has-text('Enviar')"
                )

                if not submit_btn:
                    # No form found — likely a login/register wall
                    await browser.close()
                    return "needs-registration"

                # Fill profile fields
                for field in self.profile_fields:
                    name = field.get("name", "")
                    value = field.get("value", "")
                    if not value:
                        continue
                    try:
                        selector = f"input[name='{name}'], textarea[name='{name}'], "
                        f"input[id='{name}'], textarea[id='{name}'], "
                        f"input[placeholder*='{name}']"
                        await page.fill(selector, value)
                    except Exception:
                        pass  # Field not found — skip gracefully

                # Attach CV if provided
                if self.cv_path:
                    try:
                        file_input = await page.query_selector(
                            "input[type='file']"
                        )
                        if file_input:
                            await page.set_input_files(
                                "input[type='file']", self.cv_path
                            )
                    except Exception:
                        pass

                # Submit
                try:
                    await submit_btn.click()
                    await page.wait_for_timeout(3000)
                    await browser.close()
                    return "postulado"
                except Exception:
                    await browser.close()
                    return "general-error"

        except Exception:
            return "general-error"
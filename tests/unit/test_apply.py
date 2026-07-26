"""Unit tests for src/apply package — classifier and AutoApply."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.apply.classifier import classify_outcome


# =============================================================================
# Task 1.1 — Package import
# =============================================================================


class TestApplyPackage:
    """src/apply/__init__.py must export classifier and AutoApply."""

    def test_package_imports(self):
        """RED: src/apply should import without errors."""
        import src.apply  # noqa: F811

    def test_exports_classify_outcome(self):
        """RED: src/apply should export classify_outcome."""
        import src.apply
        assert hasattr(src.apply, "classify_outcome")

    def test_exports_auto_apply(self):
        """RED: src/apply should export AutoApply class."""
        import src.apply
        assert hasattr(src.apply, "AutoApply")


# =============================================================================
# Task 2.1 — classifier (pure functions)
# =============================================================================


class TestClassifier:
    """classify_outcome maps outcome strings to status values."""

    def test_success_returns_postulado(self):
        """RED: success outcome should map to 'postulado'."""
        result = classify_outcome("success")
        assert result == "postulado"

    def test_timeout_returns_unavailable(self):
        """RED: timeout outcome should map to 'auto-apply-failed-unavailable'."""
        result = classify_outcome("timeout")
        assert result == "auto-apply-failed-unavailable"

    def test_404_returns_unavailable(self):
        """TRIANGULATE: 404 should map to 'auto-apply-failed-unavailable'."""
        result = classify_outcome("404")
        assert result == "auto-apply-failed-unavailable"

    def test_network_error_returns_unavailable(self):
        """TRIANGULATE: network_error should map to 'auto-apply-failed-unavailable'."""
        result = classify_outcome("network_error")
        assert result == "auto-apply-failed-unavailable"

    def test_register_wall_returns_needs_registration(self):
        """RED: register_wall should map to 'needs-registration'."""
        result = classify_outcome("register_wall")
        assert result == "needs-registration"

    def test_login_required_returns_needs_registration(self):
        """TRIANGULATE: login_required should map to 'needs-registration'."""
        result = classify_outcome("login_required")
        assert result == "needs-registration"

    def test_unknown_returns_general_error(self):
        """RED: unknown outcome should map to 'general-error'."""
        result = classify_outcome("some_weird_error")
        assert result == "general-error"

    def test_empty_returns_general_error(self):
        """TRIANGULATE: empty string should map to 'general-error'."""
        result = classify_outcome("")
        assert result == "general-error"


def _make_mock_playwright(mock_page=None) -> tuple[MagicMock, MagicMock]:
    """Helper to build mock Playwright hierarchy.

    Returns (mock_playwright, mock_pw_ctx) where mock_pw_ctx is the
    async context manager for async_playwright().
    """
    if mock_page is None:
        mock_page = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_playwright = MagicMock()
    mock_playwright.chromium = AsyncMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw_ctx = AsyncMock()
    mock_pw_ctx.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_pw_ctx.__aexit__ = AsyncMock()

    return mock_playwright, mock_pw_ctx


# =============================================================================
# Task 2.2 — AutoApply with mocked Playwright
# =============================================================================


class TestAutoApply:
    """AutoApply class with mocked browser operations."""

    @pytest.mark.asyncio
    async def test_apply_success_returns_postulado(self):
        """RED: successful submission should return 'postulado'."""
        from src.apply.auto_apply import AutoApply

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.fill = AsyncMock()
        mock_page.set_input_files = AsyncMock()
        mock_submit_btn = AsyncMock()
        mock_submit_btn.click = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_submit_btn)
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.click = MagicMock()

        _, mock_pw_ctx = _make_mock_playwright(mock_page)

        applier = AutoApply(profile_fields=[], cv_path=None)
        with patch("src.apply.auto_apply.async_playwright", return_value=mock_pw_ctx):
            result = await applier.apply("https://example.com/job/1")

        assert result == "postulado"

    @pytest.mark.asyncio
    async def test_apply_timeout_returns_unavailable(self):
        """RED: page timeout should return 'auto-apply-failed-unavailable'."""
        from src.apply.auto_apply import AutoApply

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=Exception("Timeout 30000ms exceeded"))

        _, mock_pw_ctx = _make_mock_playwright(mock_page)

        applier = AutoApply(profile_fields=[], cv_path=None)
        with patch("src.apply.auto_apply.async_playwright", return_value=mock_pw_ctx):
            result = await applier.apply("https://example.com/job/1")

        assert result == "auto-apply-failed-unavailable"

    @pytest.mark.asyncio
    async def test_apply_no_submit_button_returns_needs_registration(self):
        """RED: no submit button found should return 'needs-registration'."""
        from src.apply.auto_apply import AutoApply

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)  # no submit button

        _, mock_pw_ctx = _make_mock_playwright(mock_page)

        applier = AutoApply(profile_fields=[], cv_path=None)
        with patch("src.apply.auto_apply.async_playwright", return_value=mock_pw_ctx):
            result = await applier.apply("https://example.com/job/1")

        assert result == "needs-registration"

    @pytest.mark.asyncio
    async def test_apply_generic_error_returns_general_error(self):
        """RED: unexpected exception should return 'general-error'."""
        from src.apply.auto_apply import AutoApply

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.fill = AsyncMock()
        mock_page.set_input_files = AsyncMock()
        mock_submit_btn = AsyncMock()
        mock_submit_btn.click = AsyncMock(side_effect=Exception("Submit failed"))
        mock_page.query_selector = AsyncMock(return_value=mock_submit_btn)

        _, mock_pw_ctx = _make_mock_playwright(mock_page)

        applier = AutoApply(profile_fields=[], cv_path=None)
        with patch("src.apply.auto_apply.async_playwright", return_value=mock_pw_ctx):
            result = await applier.apply("https://example.com/job/1")

        assert result == "general-error"
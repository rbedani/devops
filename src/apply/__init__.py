"""Auto-apply package — outcome classifier and Playwright-based application runner."""

from src.apply.classifier import classify_outcome
from src.apply.auto_apply import AutoApply

__all__ = ["classify_outcome", "AutoApply"]
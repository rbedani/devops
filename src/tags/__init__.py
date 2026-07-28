"""Tag auto-detection engine."""

from src.tags.detector import TagDetector, TagRegistry, build_default_registry

__all__ = ["TagRegistry", "TagDetector", "build_default_registry"]

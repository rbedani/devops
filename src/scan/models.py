"""ScanPlatform model for the SCAN module.
 
Migrated from src/datos/models.py as part of the 5-layer architecture extraction.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScanPlatform:
    """A scan platform configuration (name + URL + enabled)."""

    name: str
    url: str
    id: int | None = None
    enabled: bool = True
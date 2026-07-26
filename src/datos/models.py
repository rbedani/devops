"""Data models for the datos module — profile fields, CV files, scan platforms.

These dataclasses represent domain entities stored in the jobs.db database
under three new tables (profile_fields, cv_files, scan_platforms).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProfileField:
    """A single user-defined profile field with name, type, and value."""

    name: str
    field_type: str  # numeric|alphanumeric|date|datetime|text|email|phone|url|file
    value: str = ""
    position: int = 0
    id: int | None = None


@dataclass
class CVFile:
    """Metadata for an uploaded CV PDF file stored on disk."""

    filename: str  # UUID-based
    original_name: str
    file_path: str
    uploaded_at: str
    id: int | None = None


@dataclass
class ScanPlatform:
    """A scan platform configuration (name + URL)."""

    name: str
    url: str
    id: int | None = None
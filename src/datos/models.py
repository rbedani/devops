"""Data models for the datos module — profile fields, CV files.

These dataclasses represent domain entities stored in the jobs.db database
under two tables (profile_fields, cv_files). The ScanPlatform model has been
moved to src.scan.models as part of the 5-layer architecture extraction.
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
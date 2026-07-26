"""Job listing data model with dynamic tag support."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class JobTag:
    """A single auto-detected tag on a job listing."""

    key: str
    value: str
    confidence: float = 1.0  # 0.0–1.0, how sure the detector is

    def __post_init__(self) -> None:
        self.key = self.key.lower().strip()
        self.value = self.value.strip()


@dataclass
class Job:
    """Represents a single job listing scraped from any source."""

    source: str  # e.g. "linkedin", "indeed", "computrabajo"
    title: str
    url: str
    company: str = ""
    location: str = ""
    description: str = ""
    tags: list[JobTag] = field(default_factory=list)
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None
    status: str = ""

    # -- Tag convenience accessors ------------------------------------------------

    def get_tag(self, key: str) -> str | None:
        """Return the first matching tag value or None."""
        for t in self.tags:
            if t.key == key.lower():
                return t.value
        return None

    def set_tag(self, key: str, value: str, confidence: float = 1.0) -> None:
        """Add or replace a tag."""
        self.tags = [t for t in self.tags if t.key != key.lower()]
        self.tags.append(JobTag(key=key, value=value, confidence=confidence))

    @property
    def modality(self) -> str | None:
        return self.get_tag("modalidad")

    @property
    def salary(self) -> str | None:
        return self.get_tag("salario")

    @property
    def schedule(self) -> str | None:
        return self.get_tag("horario")

    @property
    def vacancies(self) -> str | None:
        return self.get_tag("vacantes")

    @property
    def applicants(self) -> str | None:
        return self.get_tag("postulados")

    @property
    def published_date(self) -> str | None:
        return self.get_tag("fecha_publicacion")

    # -- Serialisation -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tags"] = [{"key": t.key, "value": t.value, "confidence": t.confidence} for t in self.tags]
        d["scraped_at"] = self.scraped_at.isoformat()
        d["status"] = self.status
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        """Reconstruct a Job from a SQLite row (with tags JSON)."""
        import json

        tags_raw = row["tags"] if "tags" in row.keys() else "[]"
        tags = [JobTag(**t) for t in json.loads(tags_raw)]

        return cls(
            id=row["id"],
            source=row["source"],
            title=row["title"],
            url=row["url"],
            company=row["company"] or "",
            location=row["location"] or "",
            description=row["description"] or "",
            tags=tags,
            scraped_at=datetime.fromisoformat(row["scraped_at"]),
            status=row["status"] if "status" in row.keys() else "",
        )

    def __repr__(self) -> str:
        return f"Job({self.source!r}, {self.title!r}, company={self.company!r})"

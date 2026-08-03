"""Subprocess driver for the main() SCAN_KEYWORD post-filter test (D4).

scripts.run_search swaps sys.stdout at import time (TextIOWrapper), so it
cannot be imported inside a pytest process without breaking capture — it is
executed here in a fresh interpreter instead.

Patches:
- rs.run_target -> returns one description-only match per target call
- rs.matches_any_keyword -> deliberately broken (always False)

With SCAN_KEYWORD=terraform set, main()'s post-filter must STILL keep the
desc-only job. If it routes the filter through the legacy matcher, the job
is dropped and its title never prints in the output table.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.run_search as rs  # noqa: E402
from src.core.models.job import Job  # noqa: E402

DESC_ONLY_JOB = Job(
    source="test",
    title="Platform SRE Engineer",
    url="https://example.com/terraform-infra",
    company="Acme",
    description="We need terraform for our infra",
)


async def fake_run_target(
    target, db, target_index=0, total_targets=1, max_jobs=None, env_overrides=None,
    max_per_keyword=None,
):
    """Return the same description-only job for every target call."""
    return [DESC_ONLY_JOB]


rs.run_target = fake_run_target
# Legacy matcher broken on purpose: only the new relevance matcher must keep
# the description-only job alive in the main() SCAN_KEYWORD post-filter.
rs.matches_any_keyword = lambda job, keywords: False  # type: ignore[assignment]

asyncio.run(rs.main())

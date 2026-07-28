"""Scan state management and subprocess adapter for dashboard scan execution.

Migrated from src/dashboard/scan.py as part of the 5-layer architecture extraction.
Launches run_search.py as a subprocess, streams stdout for progress tracking,
and maintains a singleton ScanState for SSE-based progress reporting.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field

# Map DB display names → internal platform slugs used by run_search.py
# The dashboard stores user-friendly names in scan_platforms, while
# run_search.py's SCRAPE_PLATFORM filter matches against SearchTarget.platform
# (e.g. "wttj", "linkedin"). This lookup bridges the two worlds.
PLATFORM_SLUG_MAP: dict[str, str] = {
    "linkedin": "linkedin",
    "infojobs": "infojobs",
    "indeed": "indeed",
    "tecnoempleo": "tecnoempleo",
    "welcome to the jungle": "wttj",
}


def _platform_slug(display_name: str) -> str:
    """Convert a DB display name to an internal platform slug."""
    key = display_name.strip().lower()
    return PLATFORM_SLUG_MAP.get(key, key)


def sanitize_keyword(keyword: str, max_length: int = 200) -> str:
    """Strip shell-dangerous characters and truncate to max_length.

    Removes characters that could enable injection via subprocess env:
    ; & | $ ( ) { } < > ` ! # = % ~ ^ [ ]

    Allows alphanumeric, spaces, hyphens, underscores, dots, commas,
    colons, forward slashes, @, and +.
    """
    sanitized = re.sub(r'[;&|$(){}<>`!#=%~^\[\]]', '', keyword)
    return sanitized[:max_length]


@dataclass
class ScanState:
    """Tracks the progress of an ongoing scan operation.

    Shared singleton used by the SSE endpoint (GET /scan/status) to stream
    progress events and by run_scan() to write progress updates.

    The cancel event is an asyncio.Event that, when set, signals run_scan()
    to terminate the current subprocess and break the platform loop.
    """

    running: bool = False
    progress_pct: float = 0.0  # 0–100
    current_target: str = ""  # e.g. "devops_espana"
    targets_completed: int = 0
    targets_total: int = 0
    log_lines: list[str] = field(default_factory=list)
    error: str | None = None
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    _scan_task: asyncio.Task | None = None  # retained reference to prevent GC

    def reset(self) -> None:
        """Reset all fields to default values (idempotent)."""
        self.running = False
        self.progress_pct = 0.0
        self.current_target = ""
        self.targets_completed = 0
        self.targets_total = 0
        self.log_lines.clear()
        self.error = None
        self.cancel = asyncio.Event()  # fresh, not set
        self._scan_task = None


scan_state = ScanState()  # module-level singleton


async def run_scan(
    state: ScanState,
    debug: bool = False,
    keyword: str = "",
    platforms: list[str] | None = None,
    location: str = "",
    modality: list[str] | None = None,
    date_range: str = "",
) -> None:
    """Launch run_search.py as subprocess once per platform and parse stdout for progress.

    Divides progress evenly across platforms. Each platform subprocess gets its
    own SCRAPE_PLATFORM env var. Updates the provided ScanState in-place as
    each platform's lines are read.

    Subprocess command: sys.executable -m scripts.run_search
    When debug=True, sets DEBUG_MODE=3 to limit results per scraper.
    When keyword is non-empty, sets SCAN_KEYWORD env var so the subprocess
    can apply a post-scrape title/company filter.
    When location is non-empty, sets SCAN_LOCATION env var for search geo.
    When modality is non-empty, sets SCAN_MODALITY env var for work type.
    When date_range is non-empty, sets SCAN_DATE_RANGE env var for time filter.
    When platforms is provided, sets SCRAPE_PLATFORM env var and iterates.
    Defaults to ["linkedin"] when platforms is None or empty.
    """
    state.error = None
    state.cancel.clear()
    selected = platforms or ["linkedin"]
    total_platforms = len(selected)
    state.targets_total = total_platforms

    try:
        for i, platform in enumerate(selected):
            if state.cancel.is_set():
                break

            state.current_target = platform

            env = os.environ.copy()
            env["SCRAPE_PLATFORM"] = _platform_slug(platform)
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"   # prevent espa�a on Windows
            if debug:
                env["DEBUG_MODE"] = "3"
            if keyword:
                env["SCAN_KEYWORD"] = sanitize_keyword(keyword)
            # Always set location, modality, and date_range —
            # empty string means "no filter" (override config default)
            env["SCAN_LOCATION"] = location
            env["SCAN_MODALITY"] = ",".join(modality) if modality else ""
            env["SCAN_DATE_RANGE"] = date_range

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "scripts.run_search",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )

            PROGRESS_RE = re.compile(r"^PROGRESS:([^:]+):([\d.]+)%$")

            assert proc.stdout is not None
            async for line_raw in proc.stdout:
                if state.cancel.is_set():
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=0.5)
                    except TimeoutError:
                        proc.kill()
                        await proc.wait()
                    break

                line = line_raw.decode("utf-8", errors="surrogateescape").rstrip("\n")
                m = PROGRESS_RE.match(line)
                if m:
                    target_name = m.group(1)
                    pct = float(m.group(2))
                    state.progress_pct = pct
                    state.current_target = target_name
                else:
                    state.log_lines.append(line)

            await proc.wait()
            if proc.returncode != 0 and not state.cancel.is_set():
                state.error = f"Platform '{platform}' failed with exit code {proc.returncode}"

            state.targets_completed = i + 1
            state.progress_pct = min(100.0, round(((i + 1) / total_platforms) * 100, 1))
    finally:
        state.running = False
        # Don't set 100% if cancelled or errored
        if not state.cancel.is_set() and not state.error:
            state.progress_pct = 100.0
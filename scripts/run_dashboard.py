#!/usr/bin/env python3
"""Dashboard server entry point — uvicorn with DASHBOARD_PORT config.

Usage:
    DASHBOARD_PORT=3311 python scripts/run_dashboard.py

Defaults to port 3311 if DASHBOARD_PORT is not set.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so uvicorn can resolve "src.dashboard.server"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import uvicorn


def main() -> None:
    """Start the dashboard server on the configured port."""
    port = int(os.environ.get("DASHBOARD_PORT", "3311"))
    uvicorn.run(
        "src.dashboard.server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
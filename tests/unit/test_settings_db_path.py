"""Unit tests for DB_PATH env-driven resolution (spec: db-path-resolution).

DB_PATH must resolve at import time from the DB_PATH environment variable,
falling back to PROJECT_ROOT/jobs.db when unset or empty. Resolution is
checked in a fresh interpreter (subprocess) — never importlib.reload —
because modules cache the constant at import time.
"""

from __future__ import annotations

import os
import subprocess
import sys

from src.core.config.settings import PROJECT_ROOT

_PROBE_DB_PATH = "from src.core.config.settings import DB_PATH; print(DB_PATH)"
_PROBE_OTHER_PATHS = (
    "from src.core.config.settings import DATA_DIR, CV_DIR, TARGETS_PATH, VAULT_FILE\n"
    "print(DATA_DIR)\nprint(CV_DIR)\nprint(TARGETS_PATH)\nprint(VAULT_FILE)"
)
_PROBE_IMPORT_TIME = (
    "from src.core.config.settings import DB_PATH as before\n"
    "import os\n"
    "os.environ['DB_PATH'] = '/tmp/late-set.db'\n"
    "from src.core.config.settings import DB_PATH as after\n"
    "print(before)\nprint(before == after)"
)


def _probe(code: str, *, env_db_path: str | None = None) -> str:
    """Run the probe in a fresh interpreter and return its combined output."""
    env = os.environ.copy()
    if env_db_path is None:
        env.pop("DB_PATH", None)
    else:
        env["DB_PATH"] = env_db_path
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return out.stdout.strip()


class TestDbPathResolution:
    def test_no_env_defaults_to_project_root_jobs_db(self) -> None:
        assert _probe(_PROBE_DB_PATH) == str(PROJECT_ROOT / "jobs.db")

    def test_env_set_respected(self) -> None:
        custom = "/tmp/e2e-isolation/custom.db"
        assert _probe(_PROBE_DB_PATH, env_db_path=custom) == custom

    def test_empty_env_falls_back_to_default(self) -> None:
        assert _probe(_PROBE_DB_PATH, env_db_path="") == str(PROJECT_ROOT / "jobs.db")

    def test_resolved_at_import_time(self) -> None:
        out = _probe(_PROBE_IMPORT_TIME).splitlines()
        assert out[0] == str(PROJECT_ROOT / "jobs.db")
        assert out[1] == "True"

    def test_other_paths_intact_with_env_set(self) -> None:
        lines = _probe(_PROBE_OTHER_PATHS, env_db_path="/tmp/custom.db").splitlines()
        assert lines == [
            str(PROJECT_ROOT / "data"),
            str(PROJECT_ROOT / "data" / "cv"),
            str(PROJECT_ROOT / "config" / "targets.json"),
            str(PROJECT_ROOT / ".secrets.yml"),
        ]

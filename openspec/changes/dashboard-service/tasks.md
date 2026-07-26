# Tasks: Dashboard Service Management

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150 (script 90 + test 60) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Phase 1: Foundation / Infrastructure

- [x] 1.1 Create `scripts/dashboard.sh` with shebang, license header, `set -euo pipefail`, and sourced config block (`PROJECT_ROOT`, `VENV_PYTHON`, `DASHBOARD_PORT`, `PID_FILE`).
- [x] 1.2 Implement `usage()` help function and top-level argument dispatch (case-switch) mapping `start|stop|restart|status|dev` to the corresponding function.

## Phase 2: Core Implementation

- [x] 2.1 Implement `start` — validate no PID file with live process, port availability check via `/dev/tcp`, launch `run_dashboard.py` via `nohup`, write PID to `/tmp/dashboard.pid`, confirm alive with `kill -0`.
- [x] 2.2 Implement `stop` — read PID file, send `SIGTERM`, wait up to 5s for graceful exit, remove PID file. Handle stale PID: warn and clean up without error.
- [x] 2.3 Implement `restart` — call `stop` then `start`, abort on stop failure.
- [x] 2.4 Implement `status` — check PID file existence and `kill -0` liveness, print PID and port if alive, exit 0/1.
- [x] 2.5 Implement `dev` — launch `.venv/bin/uvicorn src.dashboard.server:app --reload --reload-dir src/dashboard/templates --reload-dir src/dashboard/static` in foreground.

## Phase 3: Testing

- [x] 3.1 Create bats test: start fresh service, verify PID file, verify `kill -0`, then stop and confirm cleanup.
- [x] 3.2 Write bats test: start when already running exits non-zero; stop with stale PID file warns and cleans up; status shows PID/port when running and exits 1 when not.
- [x] 3.3 Write bats test: dev mode launches uvicorn with `--reload` flags (timeout-based, grep stderr for "Started reloader process"); port conflict detection on `start`.
- [x] 3.4 Final verification: `chmod +x scripts/dashboard.sh`, run full test suite, confirm all 5 subcommands produce correct exit codes from spec scenarios.
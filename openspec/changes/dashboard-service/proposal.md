# Proposal: Dashboard Service Management

## Intent

The dashboard process dies when the shell session ends — no persistence, no restart, no dev workflow. We need proper service lifecycle management: background daemon mode, hot-reload for development, and CLI commands to start/stop/restart without touching the existing dashboard module.

## Scope

### In Scope
- CLI script (`scripts/dashboard.sh`) with `start`, `stop`, `restart`, `status`, `dev` subcommands
- Background persistence via PID file + nohup/disown for prod
- Hot-reload dev mode via uvicorn `reload=True` + `reload_dirs=[templates/, static/]`
- PID file at `/tmp/dashboard.pid`
- Zero changes to `src/dashboard/` modules or `scripts/run_dashboard.py`

### Out of Scope
- systemd / supervisor / Docker integration
- Multi-instance management
- Log rotation
- Health check endpoints
- Port allocation beyond 3311

## Capabilities

### New Capabilities
None — pure operational tooling, no spec-level behavior.

### Modified Capabilities
None — existing `dashboard-viewer` spec requirements are unchanged.

## Approach

A single bash script `scripts/dashboard.sh` with four subcommands:

- **`start`** — runs `scripts/run_dashboard.py` via `nohup` in background, writes PID to `/tmp/dashboard.pid`, waits briefly and confirms process is alive
- **`stop`** — reads PID file, sends `SIGTERM`, removes PID file
- **`restart`** — stop + start (atomic)
- **`status`** — checks PID file, validates process is running, shows PID and port
- **`dev`** — runs uvicorn directly with `--reload --reload-dirs src/dashboard/templates --reload-dirs src/dashboard/static`, no PID file, foreground

No changes to `scripts/run_dashboard.py` or any `src/dashboard/` file. The script wraps existing entry points.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `scripts/dashboard.sh` | New | Service lifecycle CLI (start/stop/restart/status/dev) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Stale PID file after crash | Low | `stop` and `start` validate PID is alive with `kill -0` before acting |
| Port conflict | Low | `start` checks port availability before launching |
| Multiple start calls | Low | `start` refuses if PID file exists and process is alive (< `kill -0`) |

## Rollback Plan

- Delete `scripts/dashboard.sh`
- Dashboard still works via `python scripts/run_dashboard.py` directly (unchanged)

## Dependencies

- bash (available on all target systems)
- `scripts/run_dashboard.py` (exists, unchanged)

## Success Criteria

- [ ] `scripts/dashboard.sh start` launches dashboard and returns immediately
- [ ] `scripts/dashboard.sh status` shows running PID and port 3311
- [ ] Process survives shell exit (test via `ssh` or subshell)
- [ ] `scripts/dashboard.sh dev` hot-reloads on template/CSS changes
- [ ] `scripts/dashboard.sh stop` kills the process and cleans PID file
- [ ] Zero changes to `src/dashboard/` or `scripts/run_dashboard.py`
# Design: Dashboard Service CLI

## Technical Approach

Single bash script `scripts/dashboard.sh` wrapping `scripts/run_dashboard.py` for background daemon management and uvicorn dev mode. Zero changes to `src/dashboard/` or existing scripts.

Maps to [spec](../../specs/dashboard-service-cli/spec.md) requirements: each requirement maps 1:1 to a subcommand (`start`, `stop`, `restart`, `status`, `dev`).

## Architecture Decisions

### Decision: Bash over Python CLI (argparse)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| bash script | Zero install deps, native `nohup`/`kill`/PID mgmt, no subprocess overhead | **Chosen** |
| `argparse` CLI | Better error formatting, typed args, testable with pytest | Rejected — no subcommand needs structured input; all operations are native shell patterns |

### Decision: .venv Python + explicit PYTHONPATH

The editable install (`__editable__.devops-0.1.0.pth`) adds `src/` to sys.path, but the script sets `PYTHONPATH` explicitly as a safety net for environments without the editable install (fresh clone, CI, Docker). `PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"` ensures `src.dashboard.server` is always importable.

### Decision: Stale PID File Handling

| Scenario | Behavior |
|----------|----------|
| `start` sees PID file with live process | Exit non-zero, print "already running" |
| `start` sees PID file with dead process | Silently remove stale file, proceed to start |
| `stop` sees PID file with dead process | Remove stale file, print warning, exit zero |

### Decision: Port Configuration

Read `DASHBOARD_PORT` env var (default: `3311`). Passed through to `run_dashboard.py` which already reads it. The `status` command checks port occupancy via `/dev/tcp` as supplemental validation.

## Data Flow

```
User
  │  ./dashboard.sh start
  ├─→ nohup .venv/bin/python scripts/run_dashboard.py &
  │     ├─ uvicorn src.dashboard.server:app ──→ port ${DASHBOARD_PORT:-3311}
  │     └─ PID written to /tmp/dashboard.pid
  │
  ├─→ ./dashboard.sh stop
  │     ├─ kill -TERM $(cat /tmp/dashboard.pid)
  │     └─ rm /tmp/dashboard.pid
  │
  ├─→ ./dashboard.sh status
  │     ├─ kill -0 (PID alive?)
  │     └─ echo PID + port
  │
  ├─→ ./dashboard.sh restart
  │     ├─ stop (error → abort)
  │     └─ start
  │
  └─→ ./dashboard.sh dev
        └─ .venv/bin/uvicorn src.dashboard.server:app \
             --reload --reload-dirs src/dashboard/templates --reload-dirs src/dashboard/static
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `scripts/dashboard.sh` | Create | Service lifecycle CLI (start/stop/restart/status/dev) |

## Interfaces / Contracts

```bash
# Subcommand signatures
scripts/dashboard.sh start          # → exit 0 on success, exit 1+ on failure
scripts/dashboard.sh stop           # → exit 0
scripts/dashboard.sh restart        # → exit 0 or error from stop/start
scripts/dashboard.sh status         # → exit 0 if running, 1 if not
scripts/dashboard.sh dev            # → foreground, Ctrl+C to exit
```

**PID file**: `/tmp/dashboard.pid` — single line containing PID integer.
**Port source**: `DASHBOARD_PORT` env var, default `3311`.
**Python interpreter**: `.venv/bin/python` (project-local venv).
**Project root**: dirname of script's resolved symlink location.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Integration | start, stop, status, restart via actual subprocess | bats test: `run ./scripts/dashboard.sh start && run ./scripts/dashboard.sh status && run ./scripts/dashboard.sh stop` |
| Unit | Stale PID cleanup, port conflict detection | bats with mock PID file / mock occupied port (`socat` or `nc -l`) |
| Dev mode | `dev` launches uvicorn with `--reload` | bats: run with timeout, grep stderr for "Started reloader process" |

## Threat Matrix

| Boundary | Applicability | Reason |
|----------|---------------|--------|
| Documentation-like paths | N/A | No executable-file classification, no Markdown/MDX/README execution |
| Git repository selection | N/A | No git operations in script |
| Commit state | N/A | No git operations in script |
| Push state | N/A | No git operations in script |
| PR commands | N/A | No PR or VCS automation |

The script invokes controlled shell commands (`nohup`, `kill`, `rm`, `uvicorn`) with no user-supplied arguments beyond the subcommand name. Shell injection is not a vector — the script does no dynamic argument construction.

## Migration / Rollout

- Create `scripts/dashboard.sh` with `chmod +x` — no other changes.
- Existing `python scripts/run_dashboard.py` continues to work unchanged.
- **Rollback**: `rm scripts/dashboard.sh` — dashboard still works via direct Python invocation.

## Open Questions

None — spec covers all scenarios.

## Review Budget Forecast

- Single script, ~90 lines authored (shebang, help, 5 subcommands, error handling, sourcing).
- Test file ~60 lines (bats).
- **Total ~150 lines** — well within 400-line budget. Single PR.
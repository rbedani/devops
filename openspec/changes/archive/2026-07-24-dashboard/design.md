# Design: Web Dashboard for Job Listings

## Technical Approach

FastAPI + HTMX + Jinja2 web dashboard in a new `src/dashboard/` module. Zero changes to existing `src/` — the dashboard reads the same SQLite DB directly and launches scrapers via subprocess. Cyberpunk theme via CSS variables. Additive `status` column migration at startup.

Maps to [proposal](../../specs/dashboard-viewer/spec.md): each requirement (server, table, pagination, search, scan, select, debug, theme, migration) gets its own route or partial.

## Architecture Decisions

### Decision: Subprocess over Direct Import for Scan Execution

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `asyncio.create_subprocess_exec("python", "-m", "scripts.run_search")` | Isolated process, GIL-free, existing `run_search.py` unchanged, no Playwright lifecycle in dashboard process | **Chosen** |
| `import run_search; await run_search.main()` | Blocks dashboard event loop on GIL during scraping, couples Playwright browser lifecycle to uvicorn process | Rejected — subprocess is safer for long-running scraping |

### Decision: HTMX Polling for Scan Progress

| Option | Tradeoff | Decision |
|--------|----------|----------|
| SSE via `StreamingResponse` | Real-time, responsive, but requires SSE client code and separate status-tracking state | **Chosen** — FastAPI `StreamingResponse` + async generator is minimal code |
| HTMX polling (`hx-trigger="every 2s"`) | Simpler to implement, no extra JS | Rejected — less responsive, wastes requests on idle polling |
| File-based status | No server-side state, survives restarts | Rejected — file I/O overhead, stale file edge cases |

SSE endpoint `GET /scan/status` streams progress events. Dashboard writes scan state to a shared `ScanState` dataclass (in-memory, single-process). HTMX listens via `EventSource` in `script.js`.

### Decision: Dashboard-Only DB Queries

Existing `JobDatabase.get_all()` uses `limit=100` and no search/pagination. Rather than modify `src/db/` (blocked by zero-changes rule), the dashboard module queries the same SQLite DB file via `sqlite3.connect()` directly with tailored SELECTs (LIKE search, LIMIT/OFFSET pagination). Migration runs as a raw `ALTER TABLE` before the first query.

### Decision: Column Mapping

| Spec column | DB source |
|---|---|
| date_published | `tags` JSON → `fecha_publicacion` tag |
| platform | `source` column |
| title | `title` column |
| company | `company` column |
| modality | `tags` JSON → `modalidad` tag |
| salary | `tags` JSON → `salario` tag |
| location | `location` column |
| link | `url` column |
| status | new `status` column (migration) |

## Data Flow

```
Browser ──HTMX──→ FastAPI server ──→ SQLite (read)
    │                    │
    │  GET /scan         │  asyncio.create_subprocess_exec("python", "-m", "scripts.run_search")
    │←─── SSE stream ───→│
    │                    │  Scraper writes results to SQLite (existing code path)
    │  hx-trigger="load" │  After SSE "done", table partial re-fetches
    │←─── /table ─────────│
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/dashboard/__init__.py` | Create | Package marker |
| `src/dashboard/server.py` | Create | FastAPI app, routes, SSE scan status |
| `src/dashboard/scan.py` | Create | Subprocess adapter + ScanState dataclass |
| `src/dashboard/templates/base.html` | Create | Jinja2 base template with HTMX + cyberpunk shell |
| `src/dashboard/templates/index.html` | Create | Full page extending base.html |
| `src/dashboard/templates/partials/table.html` | Create | Job table body (HTMX-swappable) |
| `src/dashboard/templates/partials/progress.html` | Create | Scan progress bar partial |
| `src/dashboard/templates/partials/pagination.html` | Create | Prev/next + per-page selector |
| `src/dashboard/static/style.css` | Create | Cyberpunk theme (CSS variables, glowy borders) |
| `src/dashboard/static/script.js` | Create | Minimal JS: EventSource for SSE, select toggle |
| `scripts/run_dashboard.py` | Create | Uvicorn entry point |
| `pyproject.toml` | Modify | Add fastapi, uvicorn, jinja2, python-multipart deps |

## Interfaces / Contracts

```python
# src/dashboard/scan.py
@dataclass
class ScanState:
    running: bool = False
    progress_pct: float = 0.0      # 0–100
    current_target: str = ""        # e.g. "devops_españa"
    targets_completed: int = 0
    targets_total: int = 0
    log_lines: list[str] = field(default_factory=list)
    error: str | None = None

async def run_scan(state: ScanState) -> None:
    """Launch run_search.py as subprocess, parse stdout for progress."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "scripts.run_search",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    # Stream stdout lines, update state.progress_pct
    await proc.wait()
```

```python
# src/dashboard/server.py — key routes
@router.get("/")
async def dashboard(request: Request) -> HTMLResponse ...
@router.get("/table")
async def table(page: int = 1, per_page: int = 10, search: str = "") -> HTMLResponse ...
@router.get("/scan")
async def trigger_scan(request: Request) -> HTMLResponse ...
@router.get("/scan/status")
async def scan_status(request: Request) -> StreamingResponse ...
@router.get("/select/toggle")
async def toggle_select(request: Request) -> HTMLResponse ...
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Dashboard routes (table, pagination, search) | FastAPI `TestClient` with temp SQLite DB |
| Unit | Scan adapter (ScanState dataclass, subprocess contract) | Mock subprocess with `asyncio.create_subprocess_exec` patched |
| Unit | Migration SQL (ALTER TABLE) | Run against temp DB, verify column exists |
| Regression | All 22 existing tests | `pytest tests/` — must pass unchanged |

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|----------|---------------|-----------------|-------------------|
| Documentation-like paths | N/A — no doc-path classification or executable-file handling | — | — |
| Git repository selection | N/A — no git operations | — | — |
| Commit state | N/A — no git operations | — | — |
| Push state | N/A — no git operations | — | — |
| PR commands | N/A — no PR operations | — | — |

The subprocess call runs a known internal Python script (`scripts.run_search.py`) with no user-supplied commands, arguments, or paths. No VCS/PR automation or executable-file classification boundary exists.

## Migration / Rollout

- **Status column**: `ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT ''` executed once at dashboard startup via raw sqlite3. Wrapped in a try/except for `duplicate column` (idempotent).
- **Rollback**: Stop dashboard process, revert `pyproject.toml`, delete `src/dashboard/`. Status column is additive — safe to keep or `ALTER TABLE jobs DROP COLUMN status`.
- **No feature flags needed**. Debug checkbox controlled by `DEBUG_MODE` env var (presence check, not value).

## Open Questions

None.

## Review Budget Forecast

- Estimated ~350 lines of authored code + ~120 lines CSS/JS + ~80 lines templates = ~550 total
- Core test file (dashboard routes) ≈ 150 lines
- **Within 400-line budget?** — borderline; consider auto-chain if dashboard/ + tests exceed 400
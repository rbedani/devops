# Design: Dashboard V2 — OpenCode.ai Theme & Search Improvements

## Technical Approach

Rewrite the dashboard's cyberpunk theme to opencode.ai light, keep all functionality intact. Search input gains dual behavior: (1) debounced (2s) server-side table filter via HTMX, (2) passes its value as scan keyword to `/scan?q=...`. The subprocess receives it as `SCAN_KEYWORD` env var. Scan button disables during run via JS + server state. Progress bar replaces purple fill with #007aff neon glow. Complete CSS rewrite, minimal JS changes.

## Architecture Decisions

### Decision: Dual search behavior (filter vs scan keyword)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Separate inputs for filter and scan keyword | Clear semantics but extra UI surface | Rejected — too much clutter |
| Single input with context-aware behavior | Cleaner UX, need clear path for each action | **Chosen** — `name="search"` used by HTMX `/table` for filter; scan button includes it via `hx-include` as `q` param |
| Client-side filter (JS iterate rows) | No server load, works on cached data | Rejected — paginated data would miss rows on non-visible pages |

### Decision: Pass keyword via env var to subprocess

| Option | Tradeoff | Decision |
|--------|----------|----------|
| CLI arg (`--keyword`) | Subprocess CLI change needed | Rejected — more invasive, breaks existing callers |
| Env var `SCAN_KEYWORD` | Zero CLI change, backward compat | **Chosen** — `scan.py` adds `env["SCAN_KEYWORD"] = keyword`, `run_search.py` reads it post-scrape |

### Decision: Scan button disable mechanism

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Pure JS (listen for SSE start/end) | Works without server changes | Rejected — race condition on page load |
| Server returns `scan_state.running` in template | Deterministic initial state | **Chosen** — template gets `scan_running`, JS adds dynamic toggle on SSE events |

### Decision: Debounce increased to 2000ms

| Option | Tradeoff | Decision |
|--------|----------|----------|
| 300ms (current) | Too eager, 10+ queries during typing | Rejected |
| 2000ms | Deliberate pause after typing stops | **Chosen** — simple HTMX trigger change, no JS rewrite needed |

## Data Flow

```
User types in search ──(2s debounce)──→ HTMX GET /table?search=... ──→ SQL LIKE filter ──→ table partial
                                              │
User clicks EXECUTE SCAN ──→ HTMX GET /scan?q=<search>&debug_mode=on/off
                                  │
                                  └──→ scan.py: run_scan(keyword, debug)
                                             │
                                             └──→ subprocess: SCAN_KEYWORD=... python -m scripts.run_search
                                                           │
                                                           └──→ post-scrape filter by keyword
                                                          
SSE: /scan/status ──→ progress events ──→ JS updates progress bar
                                              │
                                              └──→ on done: htmx.trigger(#table-container, load)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/dashboard/server.py` | Modify | `/scan` accepts `q` query param, passes to `run_scan()`, passes `scan_state.running` to template |
| `src/dashboard/scan.py` | Modify | `run_scan()` accepts `keyword: str = ""`, sets `env["SCAN_KEYWORD"]` for subprocess |
| `src/dashboard/static/script.js` | Modify | Add scan button disable/enable on SSE start/done; update debounce delay in JS comment |
| `src/dashboard/static/style.css` | Rewrite | Full opencode.ai light theme: #fff bg, #1d1d1f text, #007aff accent, Berkeley Mono, flat design, neon progress bar |
| `src/dashboard/templates/base.html` | Modify | `data-theme="opencode"`, title, font link (IBM Plex Mono), remove emoji from title |
| `src/dashboard/templates/index.html` | Modify | Scan button adds `hx-include="[name='search']"`, disabled state from `scan_running`, search trigger delay to 2000ms |
| `src/dashboard/templates/partials/table.html` | Modify | Remove emoji from link cell (🔗 → text-only) |
| `src/dashboard/templates/partials/progress.html` | Modify | Add neon CSS classes reference |
| `scripts/run_search.py` | Modify | Read `SCAN_KEYWORD` env var, apply post-scrape title/company filter |
| `scripts/audit_dashboard_v2.py` | Create | Playwright validation script for theme, search, debounce, scan flow |

## Interfaces / Contracts

### `/scan` endpoint — new `q` param

```python
@app.get("/scan", response_class=HTMLResponse)
async def trigger_scan(
    request: Request,
    q: str = Query(""),        # NEW — scan keyword from search input
    debug_mode: str = Query(""),
) -> HTMLResponse:
```

### `run_scan()` — new `keyword` param

```python
async def run_scan(state: ScanState, debug: bool = False, keyword: str = "") -> None:
```

### Subprocess contract

```
env["SCAN_KEYWORD"] = keyword  # set only if non-empty
```

`run_search.py` reads `os.environ.get("SCAN_KEYWORD")` and applies:
- If set and non-empty: filter scraped jobs where keyword appears in `title` or `company` (case-insensitive substring)
- If empty/unset: no post-filter (backward compatible)

### Template extra variable

```python
# Passed to index.html:
{
    "scan_running": scan_state.running,  # NEW — for button state
    "total_jobs": total,
    "debug_mode": DEBUG_MODE,
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Scan keyword env var behavior | Mock subprocess, verify `SCAN_KEYWORD` set correctly in env |
| Unit | Post-scrape filter in run_search.py | Unit test filter function with sample jobs (no Playwright) |
| E2E | Playwright validation | `scripts/audit_dashboard_v2.py` — validate theme CSS, scan flow, debounce, progress bar |
| E2E | Scan button disabled state | Playwright: click scan, verify `disabled` attribute, wait for done, verify enabled |

## Threat Matrix

Applicable — this design modifies subprocess execution (env var injection into `run_search.py`) and adds a network input (`q` query param) that flows into subprocess environment. No `references/threat-matrix.md` exists in this repo; boundaries documented here directly:

| Boundary | Risk | Mitigation | RED Test |
|----------|------|------------|----------|
| Subprocess env var injection | Arbitrary string from URL param reaches subprocess env | Value truncated to 200 chars, alphanumeric + spaces only via sanitiser in `scan.py` | Verify special chars (`;`, `&`, `|`, `$()`) are stripped |
| Scan concurrent execution | Double-scan could corrupt state | `scan_state.running` guard at entry — second `/scan` returns existing progress, does not start new subprocess | Verify `/scan` with concurrent requests returns same progress partial |
| Keyword to SQL (filter partial) | Existing `search` param already goes through SQL LIKE | No change — existing pattern uses parameterised queries. `q` param is NOT used in SQL, only in env var | Static analysis confirms `q` never reaches SQL |

No VCS/PR automation or executable-file classification boundaries touched.

## Migration / Rollout

No migration required. Theme swap is CSS-only — all class names stay the same. Env var addition is backward compatible (empty/unset = no filter). Button disable is additive JS. Rollback: revert files, no data migration.

## Open Questions

- None

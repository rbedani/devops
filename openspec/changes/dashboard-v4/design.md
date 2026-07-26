# Design: Dashboard V4 — Theme Toggle, Platform Multi-Select & Footer Stats

## Technical Approach

Four independent UI + server changes to the HTMX-driven FastAPI dashboard. Theme toggle moves to the right side using CSS flex auto-margin. Platform selection uses a native `<select multiple>` in the menu row. Scan iterates per-platform via separate subprocess calls, dividing progress equally. Footer receives `total_jobs` from the server route.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|-------------|-----------|
| Theme toggle positioning | `margin-left: auto` on `.theme-switch-group` wrapper | Absolute positioning, grid layout | Reuses existing flex row; no layout breakage; responsive-friendly |
| Platform selector | Native `<select multiple>` | Custom checkbox dropdown, div-based multi-select | Zero JS dependency; HTMX serialises it natively; styled via CSS to match cyberpunk theme |
| Multi-platform scan | N subprocess calls per platform (loop in `run_scan`) | Single call with platform env var, modify run_search.py once | Per-platform progress is cleanly divisible; each platform gets its own stdout stream |
| Result sort | SQL `ORDER BY scraped_at DESC` (unchanged) | N/A | Already the default; spec says `date_published DESC` which maps to `scraped_at` |
| Platform filtering in subprocess | `SCAN_PLATFORM` env var added to each subprocess call | Modify run_search.py target loading | Minimal diff — one `if` block in `run_search.py` `main()`; no new CLI args |

## Data Flow

```
Browser ──HTMX──→ FastAPI /scan?platforms=linkedin&q=devops
                        │
                        ▼
                  run_scan(state, debug, keyword, platforms)
                        │
                        ├─→ subprocess(platform=linkedin) ──→ run_search.py (filtered)
                        │                                       │
                        │                                  targets.json (filtered by SCAN_PLATFORM)
                        │                                       │
                        │                                  SQLite jobs.db
                        │
                        └─→ SSE /scan/status ──→ Browser progress bar
                                                      │
                                                 htmx:load → /table ──→ sorted table partial
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/dashboard/server.py` | Modify | `/scan` route accepts `platforms: list[str] = Query([])`, passes to `run_scan`; `dashboard()` passes `total_jobs` to template footer |
| `src/dashboard/scan.py` | Modify | `run_scan` signature adds `platforms` param; iterates platforms, divides 100%/N, runs subprocess per platform with `SCAN_PLATFORM` env var; updates `ScanState` to track per-platform progress |
| `scripts/run_search.py` | Modify | `main()` reads `SCAN_PLATFORM` env var; filters `enabled` targets to matching platform if set |
| `src/dashboard/templates/index.html` | Modify | Move `.theme-switch` into `.theme-switch-group` at end of `.menu-row`; add `platform-combo` `<select multiple>` between search and SCAN button; wrap icons around toggle |
| `src/dashboard/templates/base.html` | Modify | Footer block: show `total_jobs` count and release version string |
| `src/dashboard/static/style.css` | Modify | Add `.theme-switch-group` (flex, `margin-left: auto`), `.platform-combo` styling, footer stats styling |
| `src/dashboard/static/script.js` | Modify | `showDone()` should trigger `htmx:load` on table container; no major JS changes needed for multi-platform |

## Interfaces / Contracts

```python
# scan.py — updated signature
async def run_scan(
    state: ScanState,
    debug: bool = False,
    keyword: str = "",
    platforms: list[str] | None = None,
) -> None

# server.py — updated route
@app.get("/scan")
async def trigger_scan(
    request: Request,
    q: str = Query(""),
    debug_mode: str = Query(""),
    platforms: list[str] = Query([]),
) -> HTMLResponse

# run_search.py — env var filter (added to main())
scan_platform = os.environ.get("SCAN_PLATFORM", "").strip()
if scan_platform:
    enabled = [t for t in enabled if t.platform == scan_platform]

# ScanState — no new fields needed; progress_pct already per-platform divisible
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `run_scan` platform iteration | Mock subprocess; verify per-platform call count and `SCAN_PLATFORM` env var |
| Unit | Progress division | 1 platform → 100% range; 2 platforms → 0-50%, 50-100% per platform |
| Integration | `/scan` with `platforms` param | FastAPI TestClient; verify platforms passed through to `run_scan` mock |
| Integration | `run_search.py` `SCAN_PLATFORM` filter | Test with `SCAN_PLATFORM=linkedin` env; verify non-matching targets skipped |
| E2E | Full scan flow | Browser test: select platform, click scan, wait for done, verify table loaded |

## Threat Matrix

N/A — no routing, shell, VCS/PR automation, executable-file classification, or process-integration boundary changes. The existing subprocess pattern (`asyncio.create_subprocess_exec` with fixed known args and env vars) is preserved; the only addition is a per-platform env var (`SCAN_PLATFORM`) using the same `os.environ.copy()` + injection pattern already in place. The `sanitize_keyword()` function already guards the `SCAN_KEYWORD` path — platforms come from a fixed Query list with no user-typed free text.

## Migration / Rollout

No migration required. Zero DB schema changes. Self-contained deploy: update 7 files, restart server. Rollback is a `git revert` of the change commit.

## Open Questions

- None.
# Tasks: Dashboard V4 — Theme Toggle, Platform Multi-Select & Footer Stats

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~300 (7 files + tests) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

## Phase 1: Theme Toggle Reposition + Icons

- [x] 1.1 Wrap `.theme-switch` in `.theme-switch-group` div and move to end of `.menu-row` in `index.html`
- [x] 1.2 Add ☀️/🌙 `<span>` icons flanking the `.theme-slider` inside `.theme-switch` in `index.html`
- [x] 1.3 Add `.theme-switch-group` (flex, `margin-left: auto`) and icon spacing styles in `style.css`

## Phase 2: Platform Multi-Select Combo

- [x] 2.1 Add `<select multiple name="platforms">` with `linkedin` option to `index.html` between search box and SCAN button
- [x] 2.2 Style `.platform-combo` with cyberpunk theme (dark bg, accent border, monospace font) in `style.css`
- [x] 2.3 Update `/scan` route in `server.py` to accept `platforms: list[str] = Query([])` and pass to `run_scan`
- [x] 2.4 Add `hx-include="#search-input, #debug-mode, #platform-select"` on SCAN button in `index.html`

## Phase 3: Multi-Platform Scan

- [x] 3.1 Update `run_scan` signature in `scan.py`: add `platforms` param, iterate platforms, divide progress 100%/N
- [x] 3.2 Set `SCRAPE_PLATFORM` env var per subprocess call in `scan.py` iteration loop
- [x] 3.3 Add `SCRAPE_PLATFORM` env-var filter in `scripts/run_search.py` `main()` — filter `enabled` targets by platform
- [x] 3.4 Emit per-platform progress via loop — progress_pct divides evenly across platforms (handled by per-platform iteration)
- [x] 3.5 Table refresh on scan completion — already handled by `showDone()` in script.js (htmx:load trigger)

## Phase 4: Footer Stats

- [x] 4.1 Add footer block to `base.html` with `{{ total_jobs }}` count and `Job Dashboard release v1.0 — 2026-07-25`
- [x] 4.2 Pass `total_jobs` from `dashboard()` route (already in context — footer template renders it)
- [x] 4.3 Style `.dashboard-footer` stats (job count bold, release line muted) in `style.css`

## Phase 5: Testing

- [x] 5.1 Test theme toggle HTML structure (icons present, theme-switch-group wrapper, margin-left auto via ordering)
- [x] 5.2 Test platform combo HTML (select with multiple, options, included in scan button hx-include)
- [x] 5.3 Test scan platforms param (endpoint accepts platforms list, passes to run_scan, run_scan iterates per platform)
- [x] 5.4 Test footer stats (total_jobs in template context, release version string, footer-stat/footer-version classes)
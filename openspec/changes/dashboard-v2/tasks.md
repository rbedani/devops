# Tasks: Dashboard V2 — OpenCode.ai Theme & Search Improvements

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~800 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Backend/JS) → PR 2 (CSS Theme) → PR 3 (Playwright Audit) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Backend: scan keyword, debounce, button guard | PR 1 | `pytest tests/unit/test_dashboard_backend.py -v` | N/A — unit tests with mocked subprocess | Revert `server.py`, `scan.py`, `run_search.py`, `script.js`, `index.html` |
| 2 | CSS Theme: opencode.ai light, neon bar | PR 2 | `pytest tests/unit/test_dashboard_backend.py::TestFrontendStaticAssets -v` | N/A — CSS-only + template changes, tested via FastAPI TestClient | Revert `style.css`, `base.html`, `table.html`, `progress.html` |
| 3 | Playwright Audit: validate full flow | PR 3 | `python -m pytest tests/e2e/ -v --retries=2` | `python scripts/audit_dashboard_v2.py` | Revert `scripts/audit_dashboard_v2.py` (test-only, no prod impact) |

## Phase 1: Backend / JS Logic — PR 1 (~300 lines)

- [x] 1.1 Add `q: str = Query("")` param to `trigger_scan` in `server.py`; pass as `keyword` to `run_scan()`
- [x] 1.2 Add `keyword: str = ""` param to `run_scan()` in `scan.py`; set `env["SCAN_KEYWORD"] = keyword` if non-empty
- [x] 1.3 Add post-scrape filter in `run_search.py`: read `SCAN_KEYWORD` env var, filter `title`/`company` (case-insensitive substring)
- [x] 1.4 Change search debounce in `index.html`: `delay:300ms` → `delay:2000ms`
- [x] 1.5 Add `scan_running` to `/` route context in `server.py`; add disabled attribute + muted style to scan button in `index.html` when `scan_running` is true
- [x] 1.6 Add scan button JS guard in `script.js`: on SSE start disable button, on `done` re-enable
- [x] 1.7 Add `hx-include="#search-input"` to scan button in `index.html` so search value passes as `q` param
- [x] 1.8 RED: write threat-matrix tests — verify special chars (`;`, `|`, `$()`) stripped from keyword in `scan.py`; verify `/scan` concurrent request returns same progress

## Phase 2: CSS Theme — PR 2 (~350 lines)

- [x] 2.1 Rewrite `style.css` variables: `--bg-primary: #ffffff`, `--text-primary: #1d1d1f`, `--accent: #007aff`, `--surface: #f5f5f7`, `--border: #d2d2d7`, font: `'IBM Plex Mono', monospace`
- [x] 2.2 Remove all `border-radius`, `box-shadow`, `linear-gradient` from CSS (flat design); remove cyberpunk purple/cyan colors
- [x] 2.3 Add neon progress bar CSS: `background: #007aff`, `box-shadow: 0 0 8px #007aff, 0 0 16px #007aff` on `.progress-fill`, pulse animation
- [x] 2.4 Update `base.html`: `data-theme="opencode"`, title "Job Dashboard", replace emoji in header with text, add IBM Plex Mono font link
- [x] 2.5 Update `table.html`: remove emoji from link column (`🔗 View` → `View`)
- [x] 2.6 Update `progress.html`: add neon CSS class reference
- [x] 2.7 Update `index.html`: scan button disabled style for `scan_running`; button text styling for flat theme

## Phase 3: Playwright Audit — PR 3 (~150 lines)

- [ ] 3.1 Create `scripts/audit_dashboard_v2.py` with Playwright fixture: launch browser, navigate to dashboard
- [ ] 3.2 Add test: validate CSS theme — check `background-color: #ffffff` on body, `#007aff` accent on buttons
- [ ] 3.3 Add test: type in search, wait 2s, verify table filters (debounce validation)
- [ ] 3.4 Add test: click EXECUTE SCAN, verify button `disabled`, wait for completion, verify button enabled
- [ ] 3.5 Add test: verify progress bar fill is `#007aff` blue with glow during scan
- [ ] 3.6 Add test: verify search keyword passes to scan and filters results by keyword
- [ ] 3.7 Add `--retries=2` to Playwright config for CI flakiness
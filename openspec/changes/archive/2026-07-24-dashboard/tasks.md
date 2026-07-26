# Tasks: Web Dashboard for Job Listings

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~700 (550 source + 150 tests) |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | PR 1 (Backend) → PR 2 (Templates + Assets) → PR 3 (Tests) |
| Delivery strategy | auto-chain |
| Chain strategy | **stacked-to-main** — each is additive/modular and merges independently |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Backend: deps, server.py, scan.py, migration, entry point | PR 1 | `python -c 'from src.dashboard.server import app; print("OK")'` | `DASHBOARD_PORT=9090 python scripts/run_dashboard.py & curl localhost:9090/ ; kill %1` | `git revert pyproject.toml` + `rm -rf src/dashboard/scripts/run_dashboard.py` |
| 2 | Frontend: templates + CSS + JS | PR 2 | `pytest tests/unit/test_dashboard.py -x -k test_index` | Same runtime as PR 1 (grabs templates) | `rm -rf src/dashboard/templates/ src/dashboard/static/` |
| 3 | Tests: all dashboard tests + regression | PR 3 | `pytest tests/unit/test_dashboard.py -v` | `pytest tests/` (full suite) | `git revert tests/unit/test_dashboard.py` |

## Phase 1: Foundation — Backend

- [x] 1.1 Add `fastapi`, `uvicorn`, `jinja2`, `python-multipart` to `pyproject.toml` deps
- [x] 1.2 Create `src/dashboard/__init__.py` — empty package marker
- [x] 1.3 Create `src/dashboard/scan.py` — `ScanState` dataclass + `run_scan()` async subprocess adapter
- [x] 1.4 Create `src/dashboard/server.py` — FastAPI app, Jinja2Templates, static mount, DB migration (ALTER TABLE status), all routes (GET `/`, `/table`, `/scan`, `/scan/status`, `/select/toggle`), SSE streaming for scan progress
- [x] 1.5 Create `scripts/run_dashboard.py` — uvicorn entry point with `DASHBOARD_PORT` config

## Phase 2: Frontend — Templates & Static Assets

- [x] 2.1 Create `src/dashboard/templates/base.html` — Jinja2 base shell with HTMX CDN, cyberpunk CSS vars, dark bg
- [x] 2.2 Create `src/dashboard/templates/index.html` — full page extending base.html: header menu (search, Execute Scan, Select toggle, Auto-Apply stub, Debug checkbox), table container + pagination footer
- [x] 2.3 Create `src/dashboard/templates/partials/table.html` — 9-column job table body with HTMX-swappable rows, checkbox column (conditional), status badge
- [x] 2.4 Create `src/dashboard/templates/partials/progress.html` — scan progress bar partial (cyberpunk styling)
- [x] 2.5 Create `src/dashboard/templates/partials/pagination.html` — prev/next + per-page links (10/50/100/250/All)
- [x] 2.6 Create `src/dashboard/static/style.css` — cyberpunk theme: dark bg, purple (`#a855f7`)/cyan (`#22d3ee`) accents, glowy box-shadow borders, monospace data cells, progress bar gradient
- [x] 2.7 Create `src/dashboard/static/script.js` — EventSource for SSE scan status, select-all toggle, debug checkbox logic

## Phase 3: Tests

- [ ] 3.1 Write RED test: additive migration (ALTER TABLE on temp DB, verify column + existing data preserved) — covers spec scenarios 9.1–9.2
- [ ] 3.2 Write RED test: dashboard routes (GET `/` returns 200, all 9 columns render, 3-job fixture) — covers spec scenarios 2.1–3.1
- [ ] 3.3 Write RED test: pagination (25 jobs at 10/page, page 2 shows 11–20, All shows everything) — covers spec scenarios 4.1–4.2
- [ ] 3.4 Write RED test: search filter (title/company LIKE, Engine + Designer fixture) — covers spec scenario 5.1
- [ ] 3.5 Write RED test: Auto-Apply stub (handler fires, log written, no submission) — covers spec scenario 5.2
- [ ] 3.6 Write RED test: Select toggle (hidden by default, header selects/deselects all visible) — covers spec scenario 6.1
- [ ] 3.7 Write RED test: SSE scan status progress events — covers spec scenario 7.1
- [ ] 3.8 Write RED test: Debug mode (≤2 results per scraper, hidden in production) — covers spec scenarios 8.1–8.2
- [ ] 3.9 Write GREEN implementation for all dashboard tests (make RED pass)
- [ ] 3.10 Verify regression: `pytest tests/` — all 64 existing tests pass unchanged

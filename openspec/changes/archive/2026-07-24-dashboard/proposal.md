# Proposal: Web Dashboard for Job Listings

## Intent

Job listings are only accessible via CLI/SQLite. Dashboard provides an interactive web UI to browse, filter, search, and manage scraped jobs without touching the terminal, while keeping the existing CLI 100% untouched.

## Scope

### In Scope
- FastAPI + HTMX + Jinja2 web server with cyberpunk dark theme (purple/cyan, glowy borders)
- Job table: date, platform, title, company, modality, salary, location, link, status
- Header menu: search, Execute Scan (with progress bar), Select toggle (checkbox column), Auto-Apply stub
- Pagination footer: prev/next, 10/50/100/250/all items per page
- Debug checkbox (limits scan to 2 results, removable later)
- Modular: new `src/dashboard/` module, existing code unchanged

### Out of Scope
- Auto-apply subscription (button wired via stub — future change)
- Auth, multi-user, CSV export, scheduling, WebSockets

## Capabilities

### New Capabilities
- `dashboard-viewer`: interactive web dashboard for browsing and managing scraped job listings with search, scan execution, select, and pagination

### Modified Capabilities
None

## Approach

**Web-based (FastAPI + HTMX + Jinja2 + cyberpunk CSS)** over terminal UI. CSS makes the cyberpunk theme trivial; HTMX eliminates JS for search/pagination/scan; FastAPI's async matches the Playwright scraper; separate process means CLI untouched.

Structure: `src/dashboard/server.py` (routes), `templates/` (Jinja2 partials), `static/` (CSS), `scan.py` (scraper adapter via subprocess), `scripts/run_dashboard.py` (entry point). DB: read via existing `JobDatabase`, status column added via additive migration.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/dashboard/` | New | Server, templates, static, scan adapter |
| `scripts/run_dashboard.py` | New | Entry point |
| `jobs.db` | Modified | Additive status column migration |
| `pyproject.toml` | Modified | Add fastapi, uvicorn, jinja2, python-multipart |
| `src/*` (existing) | None | No changes to scrapers, db, models, alerts |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Port conflict | Low | Configurable via `DASHBOARD_PORT` env var |
| Scan process conflict | Low | Runs via `asyncio.create_subprocess_exec` |
| CSS scope creep | Low | CSS variables + OpenCode palette reference |

## Rollback Plan

Stop process, revert `pyproject.toml`, delete `src/dashboard/`. Status column is additive — safe to keep or drop.

## Dependencies

fastapi, uvicorn, jinja2, python-multipart (add to pyproject.toml)

## Success Criteria

- [ ] Dashboard at http://localhost:8080 renders all 9 columns from jobs.db
- [ ] Pagination (prev/next, 10/50/100/250/all) works
- [ ] Search filters by title/company
- [ ] Execute Scan shows progress bar and persists to DB
- [ ] Select toggle shows checkboxes; header selects/deselects all
- [ ] Auto-Apply logs stub message (not implemented)
- [ ] All 22 unit tests pass unchanged
- [ ] Existing `scripts/run_search.py` CLI produces identical output
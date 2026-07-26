# Proposal: datos-module

## Intent

Replace the static placeholder form with a complete data/profile management module. Stores user profile fields, CV files, and scan platform configs — all prerequisites for the auto-application pipeline coming next.

## Scope

### In Scope
- Dynamic data form (add/remove custom fields, save/load from SQLite)
- PDF CV upload (upload, preview, delete, last-uploaded date)
- Platform management (LinkedIn + configurable platforms like InfoJobs)
- Date filter on GET /table (Any, 24h, Last week, Last month)
- Content-level deduplication (hash-based, beyond URL UNIQUE)

### Out of Scope
- Credentials management (deferred — 2FA blockers)
- Auto-application logic
- Scan scheduling

## Capabilities

### New Capabilities
- `data-profile`: User fields CRUD, dynamic form rendering, CV file lifecycle
- `platform-management`: Scan platform config (name + URL), CRUD, display
- `date-filter`: Date-range query param on GET /table, HTMX filter UI
- `dedup-engine`: Content hashing, duplicate detection, optional merge

### Modified Capabilities
- `dashboard-viewer`: New DATA panel sections, date filter on table header
- `dashboard-service-cli`: None

## Approach

New `src/datos/` module (modular, follows `src/dashboard/` pattern):

| Layer | Delivery |
|-------|----------|
| Models | `ProfileField`, `CVFile`, `ScanPlatform` dataclasses in `src/datos/models.py` |
| Storage | New SQLite tables (`profile_fields`, `cv_files`, `scan_platforms`) with additive migration in `src/datos/store.py` |
| Templates | HTMX partials under `src/dashboard/templates/partials/datos/` |
| Routing | FastAPI routes in `src/datos/routes.py`, mounted in server.py |

Dedup: SHA-256 of `title+company+description` added to `jobs` table, `ON CONFLICT(hash)` alongside existing `ON CONFLICT(url)`.

Date filter: New query param `since` (timedelta alias) on `/table`, Jinja2 filter dropdown + HTMX trigger.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/datos/` | New | Entire module — models, store, routes |
| `src/dashboard/server.py` | Modified | Mount datos routes, add `/table?since=` |
| `src/dashboard/templates/partials/data_form.html` | Replaced | Dynamic form with add/remove/save |
| `src/dashboard/templates/partials/table.html` | Modified | Date filter dropdown in header |
| `src/dashboard/static/script.js` | Modified | DATA button wiring, new HTMX handlers |
| `src/dashboard/static/style.css` | Modified | Form styles, CV upload, platform list |
| `src/db/database.py` | Modified | New dedup column + content hash in upsert |
| `tests/unit/test_datos.py` | New | Unit tests for datos module |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| CV file storage security (PDF access) | Low | Store in `data/cv/`, serve via authenticated route only |
| Dedup false positives (same title, diff jobs) | Med | Hash uses title+company+description; manual override in UI |

## Rollback Plan

1. Revert `server.py` routes and imports
2. Revert `database.py` changes (dedup hash column)
3. Revert templates and JS/CSS
4. Data is additive — existing `jobs` table and its URL UNIQUE constraint are untouched

## Dependencies

- Python `hashlib` (stdlib) for content hashing — no new external deps
- Existing `jobs.db` SQLite for dedup migration

## Success Criteria

- [ ] Dynamic form saves/loads custom fields to/from SQLite via HTMX
- [ ] CV upload stores PDF, shows preview link and upload date
- [ ] Platform list shows LinkedIn URL + allows add/remove of custom platforms
- [ ] Date filter returns correct subset of jobs for 24h/week/month
- [ ] Duplicate job with same content (different URL) is rejected by hash
- [ ] All TDD tests pass, no regressions in existing dashboard tests
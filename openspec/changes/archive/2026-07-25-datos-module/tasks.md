# Tasks: datos-module — Dynamic Data Form, CV Upload, Platform Management, Date Filter, Content Dedup

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~840 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Foundation + DB) → PR 2 (Templates + Frontend) → PR 3 (Tests) |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Datos module + dedup/date-filter DB | PR 1 | `pytest -v tests/unit/test_datos.py::TestStore -x` | `uvicorn src.dashboard.server:app` then POST a field via HTMX | Revert server.py + delete src/datos/ |
| 2 | Templates + JS + CSS | PR 2 | `pytest -v tests/unit/test_datos.py -k "template or js or css or integration" -x` | Load dashboard, click DATA button | Revert templates/ + script.js + style.css |
| 3 | Tests | PR 3 | `pytest -v tests/unit/test_datos.py -x` | N/A — pure test file | Revert test_datos.py |

## D1: Foundation — Datos Module (RED first: write test, then code)

- [x] **D1.1** (RED) Write test: `TestProfileField` — init, defaults, field access in `test_datos.py`
- [x] **D1.1** (GREEN) Create `src/datos/__init__.py` (empty), `src/datos/models.py` — `ProfileField`, `CVFile`, `ScanPlatform` dataclasses
- [x] **D1.2** (RED) Write test: `TestStore` — `run_datos_migration` creates 3 tables, idempotent via tmp_path
- [x] **D1.2** (GREEN) Create `src/datos/store.py` — `run_datos_migration()`, `get_connection()`, CRUD for 3 tables (fields/cv/platforms)
- [x] **D1.3** (RED) Write test: `TestRoutes` — TestClient: GET /datos/fields returns 200 HTML, POST /datos/fields/save persists
- [x] **D1.3** (GREEN) Create `src/datos/routes.py` — FastAPI APIRouter: `/datos/fields/*`, `/datos/cv/*`, `/datos/platforms/*`
- [x] **D1.4** Modify `src/dashboard/server.py` — import datos router, `app.include_router()`, call `run_datos_migration()` in lifespan

## D2: Templates — DATA Panel, Field Rows, CV, Platforms

- [x] **D2.1** (RED) Write test: `TestTemplates` — verify HTMX partials render with correct button IDs and form elements
- [x] **D2.1** (GREEN) Create `src/dashboard/templates/partials/datos/panel.html` — shell with SAVE + ADD FIELD buttons
- [x] **D2.2** (GREEN) Create `src/dashboard/templates/partials/datos/field_row.html` — single field with name/type/value/remove
- [x] **D2.3** (GREEN) Create `src/dashboard/templates/partials/datos/cv_section.html` — upload zone, preview link, delete button
- [x] **D2.4** (GREEN) Create `src/dashboard/templates/partials/datos/platforms.html` — platform list + add form + remove buttons
- [x] **D2.5** Replace `src/dashboard/templates/partials/data_form.html` — HTMX `hx-get="/datos/panel"` include

## D3: Content Dedup + Date Filter

- [x] **D3.1** (RED) Write test: `TestContentHash` — SHA-256 of known inputs, content_hash uniqueness
- [x] **D3.1** (GREEN) Modify `src/db/database.py` — add `content_hash TEXT` column migration, compute SHA-256 in `upsert_job()`, unique index + content-based dedup
- [x] **D3.2** (RED) Write test: `TestDateFilterSQL` — `_fetch_jobs` with `since=24h` returns only recent rows
- [x] **D3.2** (GREEN) Modify `src/dashboard/server.py` — add `since: str = Query("")` param to GET /table, apply WHERE `scraped_at >= datetime(...)` in `_fetch_jobs`

## D4: Frontend — Table Hash Column, Date Filter, JS Handlers, CSS

- [x] **D4.1** Modify `src/dashboard/templates/partials/table.html` — add Hash `<th>` column between link and status, add date filter `<select>` in `<thead>`
- [x] **D4.2** Modify `src/dashboard/static/script.js` — rewrite DATA button toggle to show/hide panel, add HTMX handlers for save/add/remove/upload/delete
- [x] **D4.3** Modify `src/dashboard/static/style.css` — form styles (`.data-panel`, `.data-form-group`), CV upload zone (`.cv-zone`), platform list (`.platform-item`), date filter (`.date-filter`), SAVE/ADD FIELD buttons

## D5: Tests — Unit + Integration

- [x] **D5.1** Write unit tests in `tests/unit/test_datos.py`: store CRUD (in-memory SQLite), hash dedup, date filter SQL
- [x] **D5.2** Write integration tests: TestClient verifies `/datos/fields/*`, `/datos/cv/*`, `/datos/platforms/*` return correct status codes and HTMX responses
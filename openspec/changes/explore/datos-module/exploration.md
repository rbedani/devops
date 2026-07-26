## Exploration: DATOS Module

### Current State
The project is a Playwright-based job scraper with a FastAPI dashboard (HTMX 1.9.12 + vanilla JS, ES5-compatible IIFE pattern). The DATOS button exists in the header-right area but toggles a bare-bones static form (Nombre + Apellido) with no save, no dynamic fields, no CV upload, no backend storage. The form is served via GET /data returning an empty template.

### Affected Areas
- `src/dashboard/templates/partials/data_form.html` — current placeholder form (14 lines, only Nombre + Apellido)
- `src/dashboard/static/script.js` — lines 564-590: DATA button toggle JS (saves/restores innerHTML, swaps via htmx.ajax)
- `src/dashboard/server.py` — lines 376-379: GET /data route (returns empty context)
- `src/dashboard/static/style.css` — lines 703-724: .btn-data / .btn-data-active styles, also references .form-group, .form-label, .form-input needed for data form fields
- `src/db/database.py` — SQLite JobDatabase with jobs table (id, source, title, url, company, location, description, tags, scraped_at, status)
- `src/models/job.py` — Job dataclass with dynamic tags (JobTag key/value/confidence)
- `src/dashboard/templates/base.html` — line 48: DATA button in header-right
- `src/dashboard/templates/index.html` — main-content shell with table + progress containers
- `tests/unit/test_dashboard_backend.py` — 1613 lines of tests (pytest with unittest-style, FastAPI TestClient)
- `pyproject.toml` — deps: fastapi, uvicorn, jinja2, python-multipart, htmx via CDN
- `openspec/config.yaml` — hybrid mode, strict TDD enabled

### Approaches

1. **SQLite-based personal data storage** — new `datos_personales` table with columns for name, surname, email, phone, linkedin, github, CV path, and a `plataformas` table for multi-select platform tracking
   - Pros: matches existing DB pattern, additive migration, data survives restarts
   - Cons: file upload (CV) is awkward with SQLite (store path in DB, file on disk)
   - Effort: Medium

2. **JSON file-based storage** — store personal data as JSON in a file under config/
   - Pros: simple, no migration needed, easy to backup
   - Cons: no concurrency safety, no querying, not consistent with project pattern
   - Effort: Low

3. **Separate applicant profiles module** — new `src/datos/` package with its own model, storage, service
   - Pros: clean separation, testable, follows single-responsibility
   - Cons: more files, new package, requires integration with existing dashboard routes
   - Effort: Medium-High

### Recommendation
Approach 1 (SQLite-based) is the most consistent with the project's existing patterns. The `jobs.db` already uses additive migration (ALTER TABLE ADD COLUMN) in `run_migration()`. A new table `datos_personales` can be added via the same migration pattern. CV uploads should store the file path in the DB while the actual file lives under a `uploads/` directory. Dynamic form fields can be added progressively using HTMX partial swaps.

### Risks
- Strict TDD means ALL new code must be test-first (pytest with unittest-style). The test file is already 1613 lines — a DATOS test class could bloat it further. Consider starting a dedicated `test_datos_backend.py`.
- CSS for form elements (.form-group, .form-label, .form-input) doesn't exist yet — needs to be added to style.css following the flat/cyberpunk theme (no border-radius, Press Start 2P font on labels, monospace on inputs).
- The JS IIFE pattern means any new JS for the data form must live inside that same IIFE closure. The DATA toggle already uses savedContent which won't survive page navigation — form state is transient.
- HTMX 1.9.12 has limited form support — form submissions need hx-post/hx-put with hx-target. File uploads require hx-encoding="multipart/form-data".
- The `platform-select` multi-select already exists for scan filtering — can potentially be reused for DATOS platform management.
- Date filter for dedup would need a new query param on GET /table (e.g., `from_date=2026-01-01`) and a WHERE clause extension in `_fetch_jobs()`.
- Dedup logic based on URL already exists via `ON CONFLICT(url) DO UPDATE` in `upsert_job` — but title+company dedup would need a new approach.
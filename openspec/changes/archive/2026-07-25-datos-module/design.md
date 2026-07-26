# Design: datos-module — Dynamic Data Form, CV Upload, Platform Management, Date Filter, Content Dedup

## Technical Approach

New `src/datos/` module (models, store, routes) for profile fields, CV files, and scan platforms — all in the same `jobs.db` SQLite. Dashboard modifications are additive: new FastAPI routes mounted, new HTMX partials, JS expanded inside existing IIFE, CSS additions following cyberpunk theme. Content dedup via SHA-256 in `database.py` upsert. All migrations are additive (CREATE TABLE, ALTER TABLE ADD COLUMN). No new external dependencies.

## Architecture Decisions

### Decision: Same DB for datos tables
**Choice**: Profile fields, CV files, and scan platforms share `jobs.db`.
**Alternatives considered**: Separate `profile.db` (extra connection management, cross-DB joins harder).
**Rationale**: Existing `get_connection()` pattern in server.py already connects to `jobs.db`. Adding 3 tables to the same file keeps migration simple, connection management unified, and backup atomic.

### Decision: Datos module owns its migration
**Choice**: Separate `run_datos_migration()` in `store.py`, called from server.py's lifespan after `run_migration()`.
**Alternatives considered**: Inline migration in server.py (coupling), lazy migration on first route call (race condition).
**Rationale**: Follows existing `run_migration()` precedent. Module is self-contained (testable standalone). Server lifespan guarantees single migration path.

### Decision: Content hash dedup alongside URL dedup
**Choice**: `ON CONFLICT(content_hash) DO UPDATE` with existing `ON CONFLICT(url)` preserved.
**Alternatives considered**: Replace URL-based with hash-only dedup (would break existing uniqueness).
**Rationale**: Jobs may appear on different URLs with identical content (same listing cross-posted). URL UNIQUE stays for referential integrity. Hash UNIQUE prevents content duplication. Both constraints coexist.

### Decision: Date filter preserved through pagination via hx-include
**Choice**: Add `since` input with `name="since"` and `hx-include="[name='since']"` on pagination buttons.
**Alternatives considered**: URL param only (breaks on HTMX pagination swaps), session state (server-side coupling).
**Rationale**: HTMX `hx-include` carries the filter value across all table swaps naturally. Matches existing `hx-include="#search-input"` pattern in index.html.

### Decision: CV stored at `data/cv/{uuid}.pdf`
**Choice**: Filesystem storage under `data/cv/` directory, served via authenticated FastAPI route.
**Alternatives considered**: Base64 in SQLite (bloats DB, no streaming), S3 (overkill for local tool).
**Rationale**: PDF files are binary and large — SQLite BLOB is inappropriate. Filesystem is simple, fast, and the project already uses `data/` conventions. The preview route serves via authenticated endpoint.

## Data Flow

```
User clicks DATA ──→ JS toggles panel ──→ HTMX GET /data ──→ datos/routes.py
     │                                                     │
     │   ┌─────────────────┐                  ┌────────────┘
     │   │ datos/panel.html│◄─ Jinja2 render ─┘
     │   │  ├─ SAVE btn    │
     │   │  ├─ ADD FIELD   │
     │   │  ├─ field rows  │
     │   │  ├─ CV section  │
     │   │  └─ platforms   │
     │   └─────────────────┘
     │
User selects date filter ──→ HTMX GET /table?since=24h ──→ server.py _fetch_jobs()
     │                                                     └─ WHERE scraped_at >= datetime(...)
     └─→ hx-include carries since through pagination

Scraper upserts job ──→ database.py upsert_job()
                        ├─ Computes SHA-256(title+company+description)
                        ├─ ON CONFLICT(url) DO UPDATE (existing)
                        └─ ON CONFLICT(content_hash) DO UPDATE (new)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/datos/__init__.py` | Create | Package init, empty |
| `src/datos/models.py` | Create | ProfileField, CVFile, ScanPlatform dataclasses |
| `src/datos/store.py` | Create | CRUD + migration for profile_fields, cv_files, scan_platforms tables |
| `src/datos/routes.py` | Create | FastAPI APIRouter: /datos/fields/*, /datos/cv/*, /datos/platforms/* |
| `src/dashboard/server.py` | Modify | Mount datos router, add `since` param to GET /table, call datos migration in lifespan |
| `src/db/database.py` | Modify | Add content_hash to upsert_job (SHA-256, ON CONFLICT) |
| `src/dashboard/templates/partials/data_form.html` | Replace | Include `datos/panel.html` via HTMX swap |
| `src/dashboard/templates/partials/datos/panel.html` | Create | Full DATA panel shell with SAVE + ADD FIELD buttons |
| `src/dashboard/templates/partials/datos/field_row.html` | Create | Single field row partial |
| `src/dashboard/templates/partials/datos/cv_section.html` | Create | CV upload section partial |
| `src/dashboard/templates/partials/datos/platforms.html` | Create | Platform list + add form partial |
| `src/dashboard/templates/partials/table.html` | Modify | Add Hash column, date filter dropdown in thead |
| `src/dashboard/static/script.js` | Modify | Replace DATA button toggle, add HTMX handlers for save/add/remove/upload |
| `src/dashboard/static/style.css` | Modify | Form styles, CV upload zone, platform list, date filter, SAVE/ADD FIELD buttons |
| `tests/unit/test_datos.py` | Create | Unit tests for datos module |

## Interfaces / Contracts

```python
# src/datos/models.py
@dataclass
class ProfileField:
    name: str
    field_type: str       # numeric|alphanumeric|date|datetime|text|email|phone|url|file
    value: str = ""
    position: int = 0
    id: int | None = None

@dataclass
class CVFile:
    filename: str        # UUID-based
    original_name: str
    file_path: str
    uploaded_at: str
    id: int | None = None

@dataclass
class ScanPlatform:
    name: str
    url: str
    id: int | None = None
```

```python
# src/datos/store.py — function signatures
def run_datos_migration(db_path: str) -> None
def get_connection(db_path: str = "jobs.db") -> sqlite3.Connection
def get_fields(conn) -> list[ProfileField]
def save_fields(conn, fields: list[dict]) -> None
def add_field(conn) -> ProfileField
def remove_field(conn, field_id: int) -> bool
def get_cv(conn) -> CVFile | None
def save_cv(conn, filename, original_name, file_path) -> int
def delete_cv(conn) -> bool
def get_platforms(conn) -> list[ScanPlatform]
def add_platform(conn, name: str, url: str) -> int
def remove_platform(conn, platform_id: int) -> bool
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Datos models, store CRUD (in-memory SQLite) | pytest, each table CREATE/INSERT/SELECT/DELETE |
| Unit | Content hash computation | SHA-256 of known inputs, collision test |
| Unit | Date filter SQL generation | _fetch_jobs with since param, verify WHERE clause |
| Integration | Datos routes via TestClient | GET/POST each endpoint, verify HTML responses |
| Integration | Server mount + migration | DB migration creates tables, routes return 200 |
| Integration | CV upload/lifecycle | Upload PDF, verify file + DB row, delete, verify cleanup |
| E2E | Full DATA panel flow | HTMX add/save/remove fields in sequence |

## Threat Matrix

N/A — no routing boundary (FastAPI built-in typed params; no shell/subprocess integration), no VCS/PR automation, no executable-file classification, no process-integration boundary. All new endpoints follow existing FastAPI routing patterns.

## Migration / Rollout

1. Phase 1: Migration — `run_datos_migration()` creates 3 new tables + ALTER TABLE jobs ADD COLUMN content_hash (idempotent try/except)
2. Phase 2: Datos module — models.py, store.py, routes.py deployed (no schema dependency on existing data)
3. Phase 3: Templates/JS/CSS — HTMX partials, DATA panel wiring, date filter
4. Phase 4: Database.py — content hash in upsert (backwards-compatible — missing column handled by migration guard)

Rollback: revert file changes in reverse order. Table additions are additive — no data loss on revert.

## Open Questions

None — all decisions covered by specs and existing patterns.
# Design: Dashboard V3 — Cross-Column Search & Dark Mode Toggle

## Technical Approach

Two independent features on the same dashboard page: (1) broaden the SQL `WHERE` clause in `_fetch_jobs` from 2 columns to 5, all `OR`-joined with a single param; (2) introduce a dual-theme CSS variable system gated by `[data-theme]` on `<html>`, with an inline flash-guard script and a header toggle persisted in `localStorage`.

Threat-matrix scope: **N/A** — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary is touched.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|-------------|-----------|
| Search scope | SQL `LIKE` on raw tags JSON | `json_extract` per key | Tags is a flat text column — `LIKE` on raw JSON catches all nested values (modalidad, salario, horario) in one clause. False-positive risk on key names accepted (low, keys are Spanish). |
| Theme switch | CSS custom properties + `[data-theme]` selectors | CSS-only `prefers-color-scheme`, class-based switch | CSS vars keep all values in one file; `data-theme` attribute is cleaner than toggling a class on `<body>`. `prefers-color-scheme` can't store user preference. |
| Flash prevention | Inline `<script>` in `<head>` | JS on DOMContentReady | DOMContentReady fires after first paint — the flash already happened. Inline script blocks rendering until it runs, zero flicker. |

## Data Flow

```
User types in search box
       │
       ▼
HTMX GET /table?search=...
       │
       ▼
_fetch_jobs(): SELECT * FROM jobs
  WHERE title LIKE ? OR company LIKE ?
     OR location LIKE ? OR description LIKE ?
     OR tags LIKE ?
  ORDER BY scraped_at DESC
       │
       ▼
Partial HTML → HTMX swaps #table-container

User clicks theme toggle
       │
       ▼
script.js: toggle data-theme → localStorage.setItem
       │
       ▼
CSS :root [data-theme="dark"] / [data-theme="light"]
       │
       ▼
All var(--bg-primary) etc. resolve to new palette
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/dashboard/server.py` | Modify | Expand `_fetch_jobs` WHERE from 2 to 5 columns, update query params from 2 to 5 values |
| `src/dashboard/static/style.css` | Modify | Add `[data-theme="dark"]` and `[data-theme="light"]` blocks, keep existing `:root` as light |
| `src/dashboard/static/script.js` | Modify | Add theme init + toggle handler, localStorage read/write |
| `src/dashboard/templates/base.html` | Modify | Add inline flash-guard `<script>` in `<head>`, set `data-theme="dark"` default |
| `src/dashboard/templates/index.html` | Modify | Add toggle switch (checkbox) in `.menu-row` next to search |

## Interfaces / Contracts

```python
# _fetch_jobs — same signature, broader WHERE
def _fetch_jobs(
    conn: sqlite3.Connection,
    search: str = "",
    per_page: int = 10,
    offset: int = 0,
) -> tuple[list[dict], int]:
```

```javascript
// Theme API
function getStoredTheme(): string        // localStorage.getItem('dashboard-theme') || 'dark'
function setTheme(theme: string): void    // set data-theme + localStorage
function initTheme(): void                // inline in <head>, blocks paint
```

**localStorage key**: `dashboard-theme` — values `"dark"` | `"light"`. Unknown values resolve to `"dark"`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `_fetch_jobs` search param matches across all 5 columns | Parameterized pytest with known DB rows, assert `remoto` finds tags JSON containing `"value": "remoto"` |
| Unit | Dark-mode inline script reads localStorage before render | Assert `<html data-theme="dark">` on load with no stored key |
| Unit | Toggle toggles and persists | Assert `localStorage` writes, assert `data-theme` flips |
| Unit | Light mode matches palette | Assert CSS var values resolve to `#ffffff` bg, `#007aff` accent |
| E2E | HTMX search returns correct partials | Playwright: type in search, wait for table swap, assert cell content |

## Migration / Rollout

No migration required. No DB schema changes — search is query-only. Dark mode defaults to dark; no CSS-only invariant broken. Rollback: revert all 5 files.

## Open Questions

None.

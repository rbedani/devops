# Tasks: Dashboard V3 — Cross-Column Search & Dark Mode Toggle

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~170 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

## Phase 1: Cross-Column Search (3 tasks)

- [x] 1.1 `src/dashboard/server.py` — expand `_fetch_jobs` WHERE from `title LIKE ? OR company LIKE ?` to include `location`, `description`, `tags` (all 5 columns OR-joined)
- [x] 1.2 `src/dashboard/server.py` — update bind params from 2 to 5 `search_param` values in all 3 query branches (count, paginated, non-paginated)
- [x] 1.3 Write parameterized pytest: seed known rows with `remoto` in tags JSON, assert `_fetch_jobs(search="remoto")` returns matching row

## Phase 2: Dark Mode CSS (5 tasks)

- [x] 2.1 `src/dashboard/static/style.css` — add `[data-theme="dark"]` CSS variable block: `#0a0a0f` bg, `#a855f7` purple accent, `#22d3ee` cyan accent, dark text/status variants
- [x] 2.2 `src/dashboard/static/style.css` — add `[data-theme="light"]` variable block mirroring current `:root` values for explicit light theme
- [x] 2.3 `src/dashboard/static/style.css` — override `.menu-row`, `.search-box`, `.btn-*`, `.debug-checkbox` backgrounds/borders for both themes
- [x] 2.4 `src/dashboard/static/style.css` — override `.job-table`, `.cell-*`, `.job-link`, `.status-badge-*` for both themes
- [x] 2.5 `src/dashboard/static/style.css` — override `.pagination`, `.progress-bar`, scrollbar, and responsive breakpoints for both themes

## Phase 3: Dark Mode JS + Template (4 tasks)

- [x] 3.1 `src/dashboard/templates/base.html` — add inline `<script>` in `<head>` that reads `localStorage.getItem("dashboard-theme")` and sets `document.documentElement.dataset.theme` before paint; change default `data-theme="opencode"` to `data-theme="dark"`
- [x] 3.2 `src/dashboard/static/script.js` — add `getStoredTheme()`, `setTheme(theme)`, and toggle event handler that flips `data-theme` and persists to `localStorage` key `dashboard-theme`
- [x] 3.3 `src/dashboard/templates/index.html` — add dark mode toggle switch (checkbox-style) in `.menu-row` next to search box, with `id="theme-toggle"` and HTMX-independent onChange
- [x] 3.4 Write unit tests: assert `getStoredTheme()` returns `"dark"` with no stored key, assert toggle flips `data-theme` and writes to `localStorage`
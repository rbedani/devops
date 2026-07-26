# Proposal: Dashboard V3 — Cross-Column Search & Dark Mode Toggle

## Intent

Two UX improvements on the dashboard: (1) search matches ALL columns, not just `title` and `company` — so searching "remoto" finds jobs where modality contains "remoto". (2) dark mode toggle in the header menu, persisted via `localStorage`, defaulting to dark (cyberpunk palette).

## Scope

### In Scope
- Server-side SQL `WHERE` expanded to cover: title, company, location, description, tags (raw JSON text)
- Dark mode CSS variable set (cyberpunk: `#0a0a0f` bg, `#a855f7` purple, `#22d3ee` cyan)
- Toggle switch in header menu (checkbox-style)
- `localStorage` persistence, defaults to dark on first visit

### Out of Scope
- Client-side JS filtering (stays server-side SQL)
- Color picker or multiple themes beyond dark/light
- Per-user theme overrides beyond `localStorage`
- Themed scrollbar customization

## Capabilities

### New Capabilities
None — both changes modify existing spec requirements.

### Modified Capabilities
- `dashboard-viewer` — **Header Menu**: search broadens to match all columns; dark mode toggle added
- `dashboard-viewer` — **Cyberpunk Theme**: restored as dark mode, togglable from the light mode

## Approach

### Search expansion
Replace `WHERE title LIKE ? OR company LIKE ?` with `WHERE title LIKE ? OR company LIKE ? OR location LIKE ? OR description LIKE ? OR tags LIKE ?`. Single param `%query%` reused across all five. Tags is a JSON text column — `LIKE` on raw JSON catches all nested tag values (modalidad, salario, horario, etc.) without needing `json_extract`.

### Dark mode
Two CSS `:root` blocks gated by `[data-theme="dark"]` and `[data-theme="light"]`. Dark mode uses cyberpunk originals. Light mode keeps the current opencode.ai palette. JS on load: check `localStorage.getItem("theme")`, default to `"dark"`, set `document.documentElement.dataset.theme`. Inline `<script>` in `<head>` prevents flash. Toggle switch toggles the class and persists.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/dashboard/server.py` | Modified | `_fetch_jobs()` WHERE clause expanded to all columns |
| `src/dashboard/static/style.css` | Modified | Add `[data-theme="dark"]` cyberpunk variable block |
| `src/dashboard/static/script.js` | Modified | Add dark mode init + toggle handler |
| `src/dashboard/templates/base.html` | Modified | Inline theme JS, default `data-theme="dark"` |
| `src/dashboard/templates/index.html` | Modified | Add toggle switch in header menu row |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Tags `LIKE` matches false positives on key names | Low | Keys are in Spanish, user queries are in Spanish — accidental key match is unlikely to cause visible issues |
| Dark mode toggle flickers on load | Medium | Inline `<script>` in `<head>` reads `localStorage` before first paint |

## Rollback Plan

Revert `server.py`, `style.css`, `script.js`, `base.html`, `index.html`. No DB schema changes — search is query-only. Dark mode toggle defaults to dark, no CSS-only invariant broken.

## Dependencies

None.

## Success Criteria

- [ ] Search "remoto" finds jobs where title OR modality (from tags JSON) contains "remoto"
- [ ] Dark mode is default on first visit (no `localStorage` key set)
- [ ] Toggle switch persists choice across page reloads
- [ ] Light mode matches current opencode.ai palette (`#ffffff` bg, `#007aff` accent)
- [ ] Dark mode uses cyberpunk palette (`#0a0a0f` bg, `#a855f7` purple, `#22d3ee` cyan)
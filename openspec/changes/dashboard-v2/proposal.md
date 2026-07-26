# Proposal: Dashboard V2 — OpenCode.ai Theme & Search Improvements

## Intent

Current dashboard uses a cyberpunk dark theme with purple/cyan accents. The user wants: opencode.ai light theme (Apple-style, white bg, blue accent, flat minimal), debounced client-side search with dual behavior (table filter + scan keyword), neon progress bar, scan button guard, and Playwright-validated delivery.

## Scope

### In Scope
- Search input passes keyword to scan subprocess when "EXECUTE SCAN" is clicked
- Debounced (2s) client-side table filter without scan trigger
- Neon progress bar (#007aff blue with glow) during scan
- Scan button disabled while running, re-enabled on complete
- Table auto-refresh on progress bar reaching 100%
- Complete theme swap: cyberpunk → opencode.ai light (white #ffffff, text #1d1d1f, Berkeley Mono/IBM Plex Mono, accent #007aff, surface #f5f5f7, border #d2d2d7, flat/no radius/no shadow)
- Playwright evidence: validate theme, search, debounce, scan flow

### Out of Scope
- Server-side search on keystroke (removed in favor of client-side filter)
- Multi-keyword or advanced search syntax
- Persistent search state across page reloads
- Dark mode toggle
- Existing functionality: pagination, select/all, auto-apply stub, debug mode, clean DB

## Capabilities

### New Capabilities
None — all changes modify existing spec requirements.

### Modified Capabilities
- `dashboard-viewer` — **Header Menu**: search input changes from server-side HTMX (300ms) to dual behavior — client-side debounced filter (2s) + scan keyword pass-through
- `dashboard-viewer` — **Execute Scan**: accepts search keyword, button disabled while running, table auto-refreshes on completion
- `dashboard-viewer` — **Cyberpunk Theme**: replaced with opencode.ai light theme (flat, monospace, blue accent, no dark/glow elements except neon progress bar)

## Approach

**Search → Scan keyword**: Search input gains `name="search"`. Scan button's `hx-get="/scan"` includes it via `hx-include`. The `/scan` route passes it as `SEARCH_KEYWORD` env var to the subprocess. `run_search.py` applies a post-scrape title/company filter when the env var is set.

**Client-side filter (debounced 2s)**: Remove HTMX server-triggered search. Plain JS: `setTimeout` resets on each `input` event. After 2s idle, iterate visible rows and hide/show based on any-column text match (case-insensitive).

**Neon progress bar**: CSS `box-shadow: 0 0 8px #007aff, 0 0 16px #007aff` + pulse animation on fill. Same flat 3px height, but blue with glow.

**Scan guard**: JS: on scan start (`htmx:afterRequest` for `/scan`), set button `disabled` + muted opacity. On SSE `done`, restore.

**Table refresh**: `showDone()` already triggers `htmx.trigger('#table-container', 'htmx:load')` — verify and keep.

**Theme swap**: Replace all CSS variables from cyberpunk palette to opencode.ai palette. Remove emoji icons. Update `base.html` title, font links (Berkeley Mono / IBM Plex Mono via Google Fonts or CDN). Flat borders, no border-radius, no box-shadow (except neon bar).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/dashboard/static/style.css` | Modified | Complete theme rewrite: cyberpunk → opencode.ai light palette, neon progress bar CSS |
| `src/dashboard/static/script.js` | Modified | Debounced client-side filter, scan button guard, neon bar glow removal on done |
| `src/dashboard/server.py` | Modified | `/scan` route accepts `search` query param, passes to `run_scan()` |
| `src/dashboard/scan.py` | Modified | `run_scan()` accepts `keyword` arg, passes as `SEARCH_KEYWORD` env var |
| `scripts/run_search.py` | Modified | Post-scrape title/company filter when `SEARCH_KEYWORD` env var is set |
| `src/dashboard/templates/index.html` | Modified | Search input: remove HTMX trigger, add name; scan button adds hx-include |
| `src/dashboard/templates/base.html` | Modified | Theme data attribute, font links, title |
| `src/dashboard/templates/partials/table.html` | Modified | Remove emoji from link cell |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Client-side filter shows wrong data on paginated pages | Medium | Filter only visible rows; pagination still server-driven. Non-visible pages unaffected |
| Theme swap breaks existing partials | Low | CSS variables isolate palette — only var values change, class names stay |
| Scan keyword env var not read by subprocess | Low | Test with empty keyword (no-op filter) to verify backward compat |
| Playwright flakiness on CI | Medium | Use `--retries=2` and `waitForSelector` with generous timeouts |

## Rollback Plan

- Revert all `openspec/changes/dashboard-v2/` files
- `git revert` the merge commit
- Restore `style.css`, `script.js`, `server.py`, `scan.py`, `run_search.py`, templates from the previous commit
- Verify dashboard starts and cyberpunk theme renders correctly
- Status column and DB schema unchanged — no data migration needed

## Dependencies

- Berkeley Mono / IBM Plex Mono font availability (Google Fonts `IBM Plex Mono` is free; Berkeley Mono requires purchase — fallback to IBM Plex Mono)
- Playwright installed in test environment
- `reports/opencode-design.json` already captured for reference

## Success Criteria

- [ ] Search text passes to scan subprocess and filters results by keyword
- [ ] Client-side table filter activates after 2s of typing inactivity
- [ ] Scan button disabled during scan, re-enabled on complete
- [ ] Progress bar uses #007aff blue neon glow while loading
- [ ] All cyberpunk theme elements replaced with opencode.ai light theme
- [ ] Playwright tests pass validating theme, search, debounce, and scan flow
- [ ] Existing dashboard + CLI tests still pass

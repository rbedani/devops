# Proposal: Dashboard V4 — Theme Toggle Reposition, Platform Multi-Select & Footer Stats

## Intent

Move the theme toggle to a more intuitive right-side position, enable multi-platform scan
selection via a dropdown combo, show per-platform progress across all selected platforms,
and surface total job count with a release version badge in the footer.

## Scope

### In Scope
1. Theme toggle repositioned to the right side of the header with sun/moon icons
2. Platform multi-select dropdown combo in the header menu
3. Multi-platform scan: SCAN iterates selected platforms, progress bar spans all
4. Footer stats: total job count + release version

### Out of Scope
- Adding new scraper platforms (UI selects from existing, not manages)
- Auto-Apply actual submission (remains stub)
- Platform CRUD management UI

## Capabilities

### New Capabilities
- `dashboard-footer`: Footer panel displaying total stored job count and release version tag

### Modified Capabilities
- `dashboard-viewer`/Header Menu: Theme toggle repositioned to right; platform multi-select combo added
- `dashboard-viewer`/Execute Scan: `platforms` query param, multi-platform iteration, result sort by `date_published DESC`
- `dashboard-viewer`/Cyberpunk Theme: Sun/moon icon styling for theme switch

## Approach

- **Theme toggle**: Move `.theme-switch` to a new `.menu-right` container after all buttons.
  Add `<span>☀️</span>` (left) and `<span>🌙</span>` (right) flanking the slider.
- **Platform combo**: Add `<select multiple>` or checkbox dropdown with `platforms[]` name.
  Hardcode `linkedin` as initial option; designed for easy extension.
- **Scan loop**: `/scan` route accepts `platforms: list[str] = Query(["linkedin"])`.
  `run_scan` divides 100% equally: e.g., 2 platforms → 50% each. Progress events emit
  `current_platform` so the UI shows which platform is active.
- **Table sort**: On scan completion, HTMX triggers table reload with `?sort_by=date_published&sort_dir=desc`.
- **Footer**: `dashboard()` route passes `total_jobs` to `base.html` footer block.
  Release line hardcoded: `Job Dashboard release v1.0 — 2026-07-25`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/dashboard/server.py` | Modified | `/scan` accepts `platforms` param; `/table` accepts `sort_by`; footer passes total_jobs |
| `src/dashboard/scan.py` | Modified | `run_scan` accepts platform list, divides progress across platforms |
| `src/dashboard/templates/index.html` | Modified | Theme toggle moved, platform combo added |
| `src/dashboard/templates/base.html` | Modified | Footer block with stats and release version |
| `src/dashboard/static/style.css` | Modified | Platform combo, footer stats, sun/moon icon styles |
| `src/dashboard/static/script.js` | Modified | Progress tracking per platform, table refresh on completion |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scan runs sequentially per platform — total time multiplies | Medium | Show per-platform progress in real-time; progress bar always moves forward |
| Platform list hardcoded to `[linkedin]` — new platforms need code change | Low | Use a constant list in server.py; one-line add |

## Rollback Plan

Revert all 6 files to pre-v4 state. No DB schema changes — data intact. No migration
needed.

## Dependencies

None. Self-contained UI + server changes.

## Success Criteria

- [ ] Theme toggle renders on right side of header with sun/moon icons; old position empty
- [ ] Platform combo renders with `linkedin` checked by default
- [ ] SCAN iterates each selected platform; progress bar spans all
- [ ] Table refreshes sorted by `date_published DESC` on completion
- [ ] Footer shows total job count and `Job Dashboard release v1.0 — 2026-07-25`
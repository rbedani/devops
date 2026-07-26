# Proposal: Flat Design + Playwright Audit

## Intent

Two concrete deliverables: (1) **flat CSS refactor** — remove all `border-radius`, `box-shadow`, border glows, and rounded decorations from the dashboard, preserving only the cyberpunk color palette (`#0a0a0f`, `#a855f7`, `#22d3ee`); (2) **Playwright audit script** that proves the debug mode flow works end-to-end with visual evidence.

## Scope

### In Scope
- Strip all `border-radius` from `style.css` (menu row, buttons, table, badges, pagination bar, scrollbar thumb, link pills)
- Strip all `box-shadow` and glow effects (`text-shadow`, `border-glow`, shadow variables)
- Convert rounded/pill status badges to flat rectangles (`border-radius: 0`)
- Remove gradient backgrounds from `.btn-scan` and progress fill (flat solid colors instead)
- Remove `text-shadow` from dashboard title
- Keep all CSS variables for cyberpunk palette intact — only remove shape/glow properties
- Write `scripts/audit_flat.py` — Playwright script that screenshots the full debug flow

### Out of Scope
- No HTML template changes (structure stays identical)
- No JS changes (behavior unmodified)
- No server-side changes
- No color palette changes — `#a855f7`, `#22d3ee`, `#0a0a0f` remain

## Capabilities

### New Capabilities
- `flat-audit`: Playwright audit script for dashboard visual verification — captures debug mode flow as screenshots

### Modified Capabilities
- `dashboard-viewer`: **Requirement: Cyberpunk Theme** — changes from "glowy box-shadow borders" to "flat aesthetic with cyberpunk palette". The existing spec scenario "Theme applied" must be updated to reflect flat styling.

## Approach

**Flat CSS**: One pass through `style.css`: replace every `border-radius: Npx` with `border-radius: 0`, remove all `box-shadow` declarations, replace gradient backgrounds with solid fills, and delete shadow/glow CSS variables. The color palette CSS variables stay.

**Playwright audit**: A self-contained Python script using `playwright.sync_api` that:
1. Launches headless Chromium at `http://localhost:3311`
2. Screenshots initial dashboard state → `reports/flat-audit/01-initial.png`
3. Clicks the DEBUG checkbox → screenshots showing CLEAN DB button → `reports/flat-audit/02-debug-on.png`
4. Clicks CLEAN DB → screenshots empty state → `reports/flat-audit/03-after-clean.png`
5. Verifies EXECUTE SCAN button exists, observes progress bar → `reports/flat-audit/04-scan-ready.png`
6. Saves combined report with all screenshots

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/dashboard/static/style.css` | Modified | Remove border-radius, box-shadow, glow effects |
| `scripts/audit_flat.py` | New | Playwright audit script |
| `openspec/specs/dashboard-viewer/spec.md` | Modified | Update Requirement: Cyberpunk Theme |
| `reports/flat-audit/` | New | Screenshot output directory |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|-------------|
| Missed shadow/radius property | Low | Grep `border-radius`, `box-shadow`, `text-shadow` in CSS — exhaustive search |
| Playwright browser crash on CI | Low | Script wraps in try/finally for browser context cleanup; `.gitignore` the reports dir |

## Rollback Plan

`git checkout HEAD -- src/dashboard/static/style.css` — single file revert. The Playwright script is additive (new file), no rollback needed.

## Dependencies

- Dashboard running at `http://localhost:3311` for Playwright audit
- `.venv/bin/playwright` with Chromium browser binaries (confirmed installed)

## Success Criteria

- [ ] `style.css` has zero `border-radius`, `box-shadow`, or `text-shadow` declarations
- [ ] Dashboard renders fully flat — no rounded corners, no glows, no shadows
- [ ] Color palette unchanged — `#a855f7` and `#22d3ee` still present
- [ ] `scripts/audit_flat.py` runs without errors
- [ ] Audit script produces 4+ screenshots in `reports/flat-audit/`
- [ ] Audit screenshots show: initial state, debug ON with CLEAN DB visible, empty state after clean, scan button
- [ ] All existing `pytest` tests pass

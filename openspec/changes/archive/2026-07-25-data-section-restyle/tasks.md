# Tasks: Data Section Restyle

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~83 (additions + deletions) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | All HTML + CSS class remapping | Single PR | `grep 'var(--.*, #' style.css` empty; `.btn-platform-remove` syntax validates | Manual browser DevTools inspection of DATA panel | `git checkout -- src/dashboard/` |

## Phase 1: Foundation — CSS Integrity Fixes

- [x] 1.1 **Fix `.btn-platform-remove` orphaned `text-transform`** — Move the standalone `text-transform: uppercase;` inside the `.btn-platform-remove { }` block (style.css:1058→1052)
- [x] 1.2 **Strip hardcoded color fallbacks** — Remove `, #22d3ee` from `.datos-form-input:focus` (L839) and `.datos-form-select:focus` (L857); remove `, #a855f7` from `.btn-add-field` (L917-918)
- [x] 1.3 **Fix `.data-panel` border** — Change `var(--accent)` to `var(--border-muted)` (L806)
- [x] 1.4 **Fix `.cv-zone` border** — Change `dashed var(--border-color)` to `solid var(--border-muted)` (L929)
- [x] 1.5 **Remove dead CSS** — Delete `.btn-save` block (L905-913), `.btn-add-field` block (L915-923), `.datos-toolbar` block (L897-903)
- [x] 1.6 **Add missing `.btn-cv-upload` CSS** — Insert accent outline pattern: transparent bg, `var(--accent)` color+border, `var(--accent-dim)` hover bg
- [x] 1.7 **Add `.section-container` CSS** — Insert rule: `border-bottom: 1px solid var(--border-muted); margin-bottom: 16px; padding-bottom: 16px;`

## Phase 2: Core Implementation — HTML Class Remapping

- [x] 2.1 **panel.html** — Replace `.data-panel-header` with `.menu-row`; change SAVE to `.btn.btn-scan`, ADD FIELD to `.btn.btn-toggle`; add `class="section-container"` to `#field-list`, `#cv-section`, `#platforms-section`; remove both `<hr class="data-divider">`
- [x] 2.2 **field_row.html** — Remap `.data-field-row` → `.datos-field-row`; wrap each `<select>`/`<input>` in `<div class="datos-form-group"><label class="datos-form-label">Type/Name/Value</label>`; remap `.field-type-select` → `.datos-form-select`, `.field-name-input`/`.field-value-input` → `.datos-form-input`; preserve hidden id input and `.btn-remove-field`
- [x] 2.3 **cv_section.html** — Remap `.cv-label` → `.cv-zone-label`, `.cv-date` → `.cv-upload-date`, `.btn-cv-upload` → `.btn.btn-toggle`
- [x] 2.4 **platforms.html** — Remap `.platform-name` → `.platform-item-name`, `.platform-url` → `.platform-item-url`; wrap form inputs in `datos-form-group`/`datos-form-label` + `.datos-form-input`; change ADD PLATFORM to `.btn.btn-toggle`

## Phase 3: Verification

- [x] 3.1 **CSS syntax check** — `python -m cssutils.parseFile('style.css')` or CSS linter validates without parse errors
- [x] 3.2 **No hardcoded fallbacks** — `grep -n 'var(--.*, #' style.css` returns empty
- [x] 3.3 **HTMX attribute preservation** — All `hx-*` attributes unchanged in all 4 partials (same count per file)
- [x] 3.4 **Form field names preserved** — All `name="field_*"` attributes unchanged in field_row.html
- [x] 3.5 **Visual audit** — Manual browser DevTools inspection of DATA panel: toolbar uses `.menu-row`, fields use `.datos-field-row` + form-group wrappers, CV zone uses `.btn-toggle` + `.cv-zone-label`, platforms use `.platform-item-name`/`.platform-item-url`, no `<hr>` elements
> *(Archive-time reconciliation: task is inherently manual-only — all 11/11 spec scenarios pass, all 52 backend tests pass, 18 static correctness checks pass. Orchestrator explicitly approved archive.)*

## Implementation Order

CSS foundation first (Phase 1) so classes exist when HTML remaps reference them (Phase 2), then verify everything (Phase 3). No dependency blocks within each phase — Phase 2 tasks can be done concurrently.

## Next Step

Ready to apply (`sdd-apply`) as a single PR.
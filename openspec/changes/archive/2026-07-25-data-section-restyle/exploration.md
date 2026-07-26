# Exploration: data-section-restyle

## Current State

The DATA section (panel, field rows, CV upload, platform management) was built without
following the established dashboard design system. It has its own set of CSS classes,
inconsistent button styling, no structured layout pattern, and multiple HTML/CSS class
mismatches that mean CSS rules are silently not applying.

## Discrepancies Found

### 1. HTML/CSS Class Mismatch — CRITICAL

| HTML uses | CSS defines | Status |
|---|---|---|
| `data-panel-header` | `.datos-toolbar` | **Broken** — no CSS for `.data-panel-header` |
| `data-field-row` | `.datos-field-row` | **Broken** — no CSS for `.data-field-row` |
| `field-type-select` | `.datos-form-select` | **Broken** — no CSS for `.field-type-select` |
| `field-name-input` | `.datos-form-input` | **Broken** — no CSS for `.field-name-input` |
| `field-value-input` | `.datos-form-input` | **Broken** — no CSS for `.field-value-input` |
| `platform-name` | `.platform-item-name` | **Broken** — no CSS for `.platform-name` |
| `platform-url` | `.platform-item-url` | **Broken** — no CSS for `.platform-url` |
| `platform-name-input` | `.datos-form-input` | **Broken** — no CSS for `.platform-name-input` |
| `platform-url-input` | `.datos-form-input` | **Broken** — no CSS for `.platform-url-input` |
| `cv-label` / `cv-date` | `.cv-zone-label` / `.cv-upload-date` | **Broken** — no CSS for `.cv-label`, `.cv-date` |

**Impact**: CSS rules that define the design system are not reaching the HTML. The page
renders with browser defaults for most input elements inside the panel.

**Proposed fix**: Align all HTML classes to the existing CSS class names. The CSS already
has a coherent naming scheme (`datos-*`, `platform-item-*`, `cv-*`). Fix HTML to use them.

---

### 2. No Menu-Row Wrapper — WARNING

The main dashboard wraps all controls in a `.menu-row` block:
```html
<div class="menu-row">
  <input class="search-box">  <!-- 36px height, system font, bordered -->
  <select class="platform-select">
  <button class="btn btn-scan">
  ...
</div>
```

The DATA panel toolbar uses a plain `div.data-panel-header` that gets **zero CSS** (see #1).
No `bg-secondary`, no `border`, no consistent `height: 36px` constraints.

**Proposed fix**: Either wrap the toolbar (SAVE + ADD FIELD) in a `.menu-row` to reuse
the existing pattern, or create a `.datos-toolbar` variant that mirrors `.menu-row`'s
visual contract (bg-secondary, border, consistent 36px height) but with its own
semantic class.

---

### 3. Button Theming Chaos — WARNING

Dashboard buttons use `.btn` base + variants with **accent** as the unifying color:

| Button | Theme |
|---|---|
| `.btn-scan` | `background: var(--accent)` — solid accent |
| `.btn-toggle` | `border-color: var(--accent)` — outline accent |
| `.btn-apply` | `border-color: var(--border-color)` — dim/disabled |
| `.btn-page` | `border-color: var(--accent-dim)` — subtle accent |

DATA buttons use three different colors with **no unifying base**:

| Button | Color | CSS |
|---|---|---|
| SAVE | Cyan (accent2) | `var(--accent2, #22d3ee)` |
| ADD FIELD | Purple (accent) | `var(--accent, #a855f7)` |
| REMOVE | Red (status-red) | `var(--status-red)` |
| ADD PLATFORM | Purple (accent) | `var(--accent)` |
| UPLOAD | Purple (accent) | `var(--accent)` |

**Additional issue**: `.btn-add-field` CSS uses `var(--accent, #a855f7)` — the hardcoded
`#a855f7` fallback overrides the theme system because in the dark theme `--accent` is
`#5f87ff` (blue-ish), not `#a855f7` (purple). The light theme accent is `#007aff` (blue).
So the fallback silently **breaks light theme** rendering.

**Proposed fix**: Decide a single accent strategy for the DATA section. Options:
- **Accent-only**: All primary buttons use `var(--accent)` like the main dashboard.
  Red-only for destructive (REMOVE/DELETE). This is the cleanest.
- **Accent2 for primary action**: SAVE in accent2 (cyan) as a visual "this saves data"
  differentiator, other actions in accent. This adds complexity.

Recommend: **Accent-only** — SAVE as solid accent (`.btn-scan` pattern), ADD FIELD / ADD
PLATFORM as outline accent (`.btn-toggle` pattern), REMOVE/DELETE as red outline. Remove
all hardcoded fallback colors.

---

### 4. CV Zone Uses Dashed Border — WARNING

`.cv-zone` uses `border: 2px dashed var(--border-color)`. No other element in the entire
dashboard uses dashed borders — everything is `1px solid` or `2px solid` (table header).
Dashed is a conventional "drop zone" visual, but it's an outlier.

**Proposed fix**: Use `border: 2px solid var(--border-muted)` with a hover transition to
`var(--accent)`. If the "drop zone" affordance is desired, add a dotted or different
border style only on hover/focus, but keep the default state in line with the system.

---

### 5. HR Dividers — SUGGESTION

The panel uses `<hr class="data-divider">` to separate fields / CV / platforms. There is
no `.data-divider` CSS class defined, so it renders with the browser default `<hr>` style.
The rest of the dashboard uses `border-bottom` on containers or sections for visual
separation.

**Proposed fix**: Replace `<hr>` elements with `border-bottom` on the parent sections
(e.g., `#field-list`, `#cv-section`, `#platforms-section`), matching the dashboard's
approach. Or, remove entirely and let the section containers provide spacing naturally.

---

### 6. Field Rows Lack Labels and Structure — SUGGESTION

`field_row.html` puts type select + name input + value input + REMOVE button in one row
with **no labels**, only placeholders. The CSS has `.datos-form-label` (mono, 0.5rem,
uppercase, text-secondary) that is designed for exactly this purpose but goes unused.

The main dashboard uses placeholders too, but those are single-purpose fields in a menu
bar (search, filter). The DATA section manages CRUD for multiple field types — labels
are appropriate here to reduce errors.

**Proposed fix**: Add `.datos-form-label` above each input inside the field row. Wrap
each input group in `.datos-form-group`. The CSS already defines `.datos-field-row`
with flex layout for this exact structure — it just needs the HTML to use matching classes.

---

### 7. Platform Add Form Has No Labels — SUGGESTION

The `platform-add-form` has two inputs (`name`, `url`) with only placeholders, same issue
as field rows. No `.datos-form-label`, no `.datos-form-group` wrappers.

**Proposed fix**: Add `.datos-form-label` for "Platform Name" and "URL" above each input.
Wrap in `.datos-form-group`. The CSS for `.platform-add-form .datos-form-group` already
exists at line 1072 of style.css.

---

### 8. CSS Syntax Error in btn-platform-remove — CRITICAL

```css
.btn-platform-remove {                    /* line 1052 */
    flex: 0 0 auto;
    background: transparent;
    color: var(--status-red);
    border: 1px solid var(--status-red);
}                                         /* line 1057 — CLOSES prematurely */
    text-transform: uppercase;            /* line 1058 — ORPHANED */
}                                         /* line 1059 — UNMATCHED */
```

The `text-transform: uppercase;` is dangling outside `.btn-platform-remove`. This is a
silent CSS error — the rule is ignored, but no other rules break because browsers skip
invalid statements. Also means platform REMOVE buttons may not be uppercase.

**Proposed fix**: Move `text-transform: uppercase;` inside the `.btn-platform-remove` block.

---

### 9. Missing .btn-cv-upload CSS — WARNING

`cv_section.html` uses `<button class="btn btn-cv-upload">` but there's no
`.btn-cv-upload` class in CSS. The upload button falls back to base `.btn` styles
(which use accent border), so it looks like an outline accent button (acceptable) but
the inconsistency should be resolved.

**Proposed fix**: Either add `.btn-cv-upload` CSS or use an existing variant like
`.btn-toggle` if the semantics match.

---

### 10. Panel Container Lacks Consistent Border — SUGGESTION

`.data-panel` is defined with `border: 1px solid var(--accent)` — a vibrant accent
border. The main dashboard's `.menu-row` uses `border: 1px solid var(--border-muted)`
(subtle). The data panel being a content section (not a navigation element) should
probably use `--border-muted` rather than `--accent`, which draws attention away from
the primary content (the job table).

**Proposed fix**: Change `.data-panel` border to `var(--border-muted)` to match the
dashboard's section styling. Reserve accent borders for interactive/highlight states.

---

## Summary by Severity

| # | Issue | Severity |
|---|---|---|
| 1 | HTML/CSS class mismatch (10+ classes) | CRITICAL |
| 8 | CSS syntax error (orphaned property) | CRITICAL |
| 2 | No menu-row wrapper for toolbar | WARNING |
| 3 | Button theming chaos + hardcoded color fallbacks | WARNING |
| 4 | CV zone dashed border outlier | WARNING |
| 9 | Missing .btn-cv-upload CSS | WARNING |
| 5 | HR dividers instead of border-bottom | SUGGESTION |
| 6 | Field rows lack labels | SUGGESTION |
| 7 | Platform add form lacks labels | SUGGESTION |
| 10 | Data panel uses accent border (too loud) | SUGGESTION |

## Recommended Fix Order

1. **Fix class mismatches** (#1, #8) — HTML class names must match CSS. This alone will
   resolve 80% of the visual discrepancy because the CSS already defines `.datos-field-row`,
   `.datos-form-select`, `.datos-form-input`, etc.
2. **Fix button theming** (#3, #9) — unify on accent, remove hardcoded fallsbacks, add
   missing `.btn-cv-upload` class.
3. **Add toolbar structure** (#2) — wrap toolbar in `.menu-row` or semantic equivalent.
4. **Fix CV zone** (#4) — replace dashed border with solid.
5. **Polish** (#5, #6, #7, #10) — remove `<hr>`, add labels, tone down panel border.

## Effort Estimate

**Low** — the CSS design system already exists with correct classes and spacing. The
primary work is HTML class alignment and minor CSS additions. No structural changes to
the backend or HTMX interactions are needed.

## Ready for Proposal

Yes. The analysis is complete. Proceed to sdd-propose to define scope, approach, and
rollback plan.
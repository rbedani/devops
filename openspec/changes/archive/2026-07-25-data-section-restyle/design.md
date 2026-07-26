# Design: Data Section Restyle

## Technical Approach

Pure CSS-class remapping + CSS bugfixes. Zero backend, zero HTMX handler, zero data model changes. Every visual change comes from applying existing dashboard design system classes (`menu-row`, `btn-scan`, `btn-toggle`, `datos-form-*`) to DATA section HTML, plus removing dead CSS and fixing syntax/fallback errors.

## Architecture Decisions

### Decision: Reuse `.menu-row` for toolbar (no new CSS)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| New `.datos-toolbar` class | Doubles CSS for identical layout | **Rejected** |
| Reuse existing `.menu-row` | Zero CSS, matches main dashboard precisely | **Chosen** |

`.menu-row` already provides `display: flex`, `bg-secondary`, `border: 1px solid var(--border-muted)`, and 36px button targets. The toolbar in `panel.html` changes from `<div class="data-panel-header">` to `<div class="menu-row">`.

### Decision: Replace `<hr>` with `border-bottom` on section wrappers

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Keep `<hr>` with restyle | Extra DOM node per section, non-themeable pixel height | **Rejected** |
| Section wrapper + `border-bottom` | Single CSS property, responds to theme CSS vars | **Chosen** |

Add `.section-container` class with `border-bottom: 1px solid var(--border-muted)` and `margin-bottom: 16px; padding-bottom: 16px`. Apply to `#field-list`, `#cv-section`, `#platforms-section`.

### Decision: Remove dead CSS, fix syntax errors, strip hardcoded fallbacks

Three CSS rules become unreferenced after HTML class changes: `.btn-save`, `.btn-add-field`, `.datos-toolbar`. Remove them. Fix orphaned `text-transform` in `.btn-platform-remove`. Strip `var(--accent, #a855f7)` → `var(--accent)` and `var(--accent2, #22d3ee)` → `var(--accent2)` from focus selectors.

## Data Flow

```
CSS Variables (theme) ──→ CSS Classes (design system) ──→ HTML (applied via restyle)
     │                              │                              │
     ├─ var(--accent)               ├─ .menu-row                   ├─ toolbar wrapper
     ├─ var(--border-muted)         ├─ .btn-scan                   ├─ SAVE button
     ├─ var(--accent2)              ├─ .btn-toggle                 ├─ ADD FIELD / UPLOAD / ADD PLATFORM
     ├─ var(--status-red)           ├─ .datos-field-row            ├─ field row container
     └─ var(--bg-tertiary)          ├─ .datos-form-group/label     ├─ input labels
                                    ├─ .datos-form-input/select    ├─ form inputs
                                    ├─ .section-container          ├─ section dividers
                                    └─ .cv-zone / .platform-item   └─ CV / platform display
```

## Component Tree (Before → After)

```
BEFORE:                              AFTER:
.data-panel                         .data-panel
├── .data-panel-header               ├── .menu-row
│   ├── .btn.btn-save                │   ├── .btn.btn-scan (SAVE)
│   └── .btn.btn-add-field           │   └── .btn.btn-toggle (ADD FIELD)
├── #field-list                      ├── #field-list.section-container
│   └── .data-field-row              │   └── .datos-field-row
│       ├── .field-type-select       │       ├── .datos-form-group/.datos-form-label + .datos-form-select
│       ├── .field-name-input        │       ├── .datos-form-group/.datos-form-label + .datos-form-input
│       ├── .field-value-input       │       ├── .datos-form-group/.datos-form-label + .datos-form-input
│       └── .btn.btn-remove-field    │       └── .btn.btn-remove-field (unchanged)
├── hr.data-divider [REMOVED]        │
├── #cv-section                      ├── #cv-section.section-container
│   └── .cv-zone (dashed)           │   └── .cv-zone (solid)
│       ├── .cv-label / .cv-date    │       ├── .cv-zone-label / .cv-upload-date
│       └── .btn.btn-cv-upload      │       └── .btn.btn-toggle (UPLOAD)
├── hr.data-divider [REMOVED]        │
└── #platforms-section               └── #platforms-section.section-container
    └── .platforms-list                  └── .platforms-list
        ├── .platform-item                   ├── .platform-item
        │   ├── .platform-name               │   ├── .platform-item-name
        │   ├── .platform-url                │   ├── .platform-item-url
        │   └── .btn.btn-platform-remove     │   └── .btn.btn-platform-remove (unchanged)
        └── .platform-add-form               └── .platform-add-form
            ├── .platform-name-input             ├── .datos-form-group/.datos-form-label + .datos-form-input
            ├── .platform-url-input              ├── .datos-form-group/.datos-form-label + .datos-form-input
            └── .btn.btn-platform-add            └── .btn.btn-toggle (ADD PLATFORM)
```

## CSS Variable Flow

| CSS Variable | Used In | Purpose |
|---|---|---|
| `var(--accent)` | `.btn-scan` bg, `.btn-toggle` color/border, `.cv-zone:hover` border, `.cv-preview-link` border | Primary accent |
| `var(--accent2)` | `.datos-form-input:focus`, `.datos-form-select:focus` border | Secondary accent for focus |
| `var(--border-muted)` | `.data-panel` border, `.menu-row` border, `.section-container` border-bottom, `.datos-field-row` border | Subtle borders |
| `var(--status-red)` | `.btn-remove-field`, `.btn-cv-delete`, `.btn-platform-remove` | Destructive actions |
| `var(--bg-secondary)` | `.data-panel` bg, `.menu-row` bg | Panel background |
| `var(--bg-tertiary)` | `.datos-field-row` bg, `.platform-item` bg | Row background |
| `var(--accent-dim)` | `.btn-toggle:hover` bg | Hover state |
| `var(--text-primary)` | `.datos-form-input` text, `.platform-item-name` | Primary text |
| `var(--text-muted)` | `.cv-zone-label`, `.platform-item-url` | Secondary text |
| `var(--text-dim)` | `.cv-upload-date` | Tertiary text |

## Layout Model

```
┌─ .data-panel (border: var(--border-muted)) ─────────────────────────┐
│                                                                      │
│ ┌─ .menu-row ──────────────────────────────────────────────────────┐ │
│ │  [SAVE .btn-scan]  [ADD FIELD .btn-toggle]                       │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌─ #field-list.section-container (border-bottom) ───────────────────┐ │
│ │  ┌─ .datos-field-row ───────────────────────────────────────────┐ │ │
│ │  │  [datos-form-group: label + .datos-form-select]              │ │ │
│ │  │  [datos-form-group: label + .datos-form-input]               │ │ │
│ │  │  [datos-form-group: label + .datos-form-input]               │ │ │
│ │  │  [.btn.btn-remove-field]                                     │ │ │
│ │  └──────────────────────────────────────────────────────────────┘ │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌─ #cv-section.section-container (border-bottom) ───────────────────┐ │
│ │  ┌─ .cv-zone (border: solid) ───────────────────────────────────┐ │ │
│ │  │  .cv-zone-label | .cv-upload-date | [PREVIEW] | [DELETE]     │ │ │
│ │  │  or: [file input] + [UPLOAD .btn.btn-toggle]                 │ │ │
│ │  └──────────────────────────────────────────────────────────────┘ │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌─ #platforms-section.section-container ────────────────────────────┐ │
│ │  ┌─ .platform-item ─────────────────────────────────────────────┐ │ │
│ │  │  .platform-item-name | .platform-item-url | [REMOVE]         │ │ │
│ │  └──────────────────────────────────────────────────────────────┘ │ │
│ │  ┌─ .platform-add-form ─────────────────────────────────────────┐ │ │
│ │  │  [datos-form-group + .datos-form-input] x 2 | [ADD .btn-toggle] │ │
│ │  └──────────────────────────────────────────────────────────────┘ │ │
│ └───────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

## Before/After Visual Diff

### Toolbar
- **Before**: Bare div with `.btn-save` (transparent, accent2 outline) and `.btn-add-field` (accent outline with hardcoded fallback `#a855f7`)
- **After**: `.menu-row` (same gray band as main dashboard header) with `.btn.btn-scan` (solid accent fill) and `.btn.btn-toggle` (accent outline, no fallback)

### Field Row
- **Before**: Bare inputs with wrong class names (`data-field-row`, `field-type-select`, `field-name-input`, `field-value-input`) — no CSS applied
- **After**: `.datos-field-row` (flex row with bg-tertiary, border-muted), each input wrapped in `.datos-form-group` + `<label class="datos-form-label">`, type select uses `.datos-form-select`

### CV Zone
- **Before**: `border: 2px dashed var(--border-color)`, labels use `.cv-label`/`.cv-date`, upload button uses bare `.btn.btn-cv-upload` (no CSS)
- **After**: `border: 2px solid var(--border-muted)` → `var(--accent)` on hover, labels use `.cv-zone-label`/`.cv-upload-date`, upload button uses `.btn.btn-toggle`

### Platform List
- **Before**: Display span uses `.platform-name`/`.platform-url` (wrong classes for existing CSS), form inputs use bare `.platform-name-input`/`.platform-url-input`
- **After**: Display spans use `.platform-item-name`/`.platform-item-url` (CSS already exists), form inputs wrapped in `.datos-form-group` + `.datos-form-input`

### Section Separators
- **Before**: `<hr class="data-divider">` between toolbar, fields, CV, platforms
- **After**: No `<hr>` elements. Each section wrapper uses `border-bottom: 1px solid var(--border-muted)` with padding/margin spacing

## Theme Compatibility

Both themes inherit through CSS variables — no hardcoded colors remain after fix:

| Element | Dark Theme | Light Theme |
|---|---|---|
| `.data-panel` border | `#555555` | `#e5e5ea` |
| `.btn-scan` bg | `#5f87ff` | `#007aff` |
| `.btn-toggle` border | `#5f87ff` | `#007aff` |
| `.datos-form-input:focus` | `#22d3ee` | `#22d3ee` |
| `.btn-remove-field` | `#ef4444` | `#ff3b30` |
| `.cv-zone` border | `#555555` → `#5f87ff` hover | `#e5e5ea` → `#007aff` hover |

## No-Regression Guarantees

| Concern | How Protected |
|---|---|
| **HTMX selectors** | All `hx-target`, `hx-swap`, `hx-post` attributes preserved verbatim. `id="field-list"`, `id="cv-section"`, `id="platforms-section"` preserved for HTMX targeting |
| **Backend routes** | Zero changes to Python handlers, URL routes, or DB models |
| **Form field naming** | `name="field_{{ id }}_type"` etc. preserved — backend receives same POST data |
| **Existing CSS** | No class removals from global namespace — only unused additions removed |
| **Responsive breakpoints** | `.menu-row` responsive behavior (stacks on mobile) is already defined in CSS at 768px |

## CSS Changes Summary

| Change | Location (line) | Action |
|---|---|---|
| `.data-panel` border: `var(--accent)` → `var(--border-muted)` | style.css:806 | Edit |
| `.datos-form-input:focus` fallback removal | style.css:839 | Edit |
| `.datos-form-select:focus` fallback removal | style.css:857 | Edit |
| Orphaned `text-transform` → inside `.btn-platform-remove` | style.css:1052-1059 | Edit |
| `.btn-save` rule block | style.css:905-913 | Delete (replaced by `.btn-scan`) |
| `.btn-add-field` rule block | style.css:915-923 | Delete (replaced by `.btn-toggle`) |
| `.datos-toolbar` rule block | style.css:897-903 | Delete (replaced by `.menu-row`) |
| `.cv-zone` border: `dashed` → `solid` | style.css:929 | Edit |
| `.btn-cv-upload` CSS: add accent outline | after style.css:1014 | Add |
| `.section-container` CSS: add border-bottom pattern | new section | Add |

## File Changes

| File | Action | Description |
|---|---|---|
| `src/dashboard/templates/partials/datos/panel.html` | Modify | Replace `.data-panel-header` → `.menu-row`, remove `<hr>`, add `.section-container` to section divs, SAVE → `.btn-scan`, ADD FIELD → `.btn-toggle` |
| `src/dashboard/templates/partials/datos/field_row.html` | Modify | Classes remapped + `.datos-form-group`/`.datos-form-label` wrappers added |
| `src/dashboard/templates/partials/datos/cv_section.html` | Modify | Labels remapped, upload button → `.btn-toggle`, border already solid in CSS |
| `src/dashboard/templates/partials/datos/platforms.html` | Modify | Classes remapped + form-group wrappers, add button → `.btn-toggle` |
| `src/dashboard/static/style.css` | Modify | Fix syntax error, strip fallbacks, fix border, add `.btn-cv-upload`, remove dead CSS, add `.section-container` |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Visual | All 4 HTML partials render with correct CSS classes | Manual inspection + browser DevTools class audit |
| CSS | `.btn-platform-remove` syntax validates | `python -m cssutils.parseFile(style.css)` or linter |
| CSS | No `var(--xxx, #rrggbb)` patterns remain | `grep 'var(--.*, #' style.css` returns empty |
| HTMX | All `hx-*` attributes preserved on changed elements | `grep` over modified templates — same count as source |
| No-regression | SAVE POST still submits field data | Verify `name="field_*"` attributes unchanged in field_row.html |

## Migration / Rollout

No migration required. HTML class changes are invisible to the backend — HTMX still targets the same IDs, form field names are preserved, backend routes unchanged. Deploy as a single commit.

## Open Questions

None.
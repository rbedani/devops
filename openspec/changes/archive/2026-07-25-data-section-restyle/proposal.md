# Proposal: Data Section Restyle — Aesthetic Alignment

## Intent

DATA section doesn't follow the dashboard's MS-DOS design system: 10+ HTML classes mismatch CSS, buttons use hardcoded colors, toolbar lacks structure, inputs render with browser defaults. Fix all visual issues to match main dashboard.

## Scope

**In**: All 10 exploration issues — class alignment, CSS syntax fix, button theming (accent-only, remove hardcoded fallbacks), toolbar → `menu-row`, CV zone dashed→solid, HR→border-bottom, field/platform labels, missing `.btn-cv-upload` CSS, panel border mute.

**Out**: Backend, HTMX handlers, data model, theme variables.

## Capabilities

New: None. Modified: None. Pure HTML/CSS restyle.

## Approach

1. **Classes**: Align HTML to existing CSS names (`.data-field-row`→`.datos-field-row`, etc.)
2. **CSS syntax**: Move orphaned `text-transform` into `.btn-platform-remove`
3. **Buttons**: SAVE = solid accent (`.btn-scan`), ADD/PLATFORM/UPLOAD = outline accent (`.btn-toggle`), REMOVE/DELETE = red outline. Kill `#a855f7`/`#22d3ee` fallbacks
4. **Toolbar**: `.menu-row` wrapper with `bg-secondary`, `border-muted`, `height:36px`
5. **CV zone**: `border: 2px solid var(--border-muted)`, hover→`var(--accent)`
6. **Dividers**: Remove `<hr>`, add `border-bottom` to section containers
7. **Labels**: `.datos-form-label` for Type/Name/Value/Platform Name/URL
8. **btn-cv-upload**: Add CSS: accent outline pattern
9. **Panel border**: `var(--accent)`→`var(--border-muted)`

**Accent decision**: **Accent-only**. SAVE = solid accent (like SCAN), not cyan. Accent2 has no semantic benefit here and would be the only place using it as a button color.

## Files

| File | Changes |
|------|---------|
| `panel.html` | `.menu-row` toolbar; remove `<hr>`; id-based borders |
| `field_row.html` | `datos-*` classes; form-group + labels |
| `field_rows.html` | Unchanged |
| `cv_section.html` | Classes aligned |
| `platforms.html` | `datos-*` classes; form-group + labels |
| `style.css` | Fallbacks removed; `.btn-cv-upload` added; syntax fixed; panel border muted |

## Risks

HTMX selectors? Low — `#id`-based. Menu-row layout break? Low — supports buttons.

## Rollback

`git checkout` all 6 files. Verify both themes visually.

## Success

- [ ] DATA panel consistent with job table in dark & light themes
- [ ] Inputs render with defined bg, border, font, focus ring
- [ ] SAVE solid accent; ADD/PLATFORM/UPLOAD outline accent; REMOVE/DELETE red outline
- [ ] CV zone solid border (no dashes)
- [ ] Labels above all inputs
- [ ] No `<hr>`, sections use `border-bottom`
- [ ] No orphaned CSS
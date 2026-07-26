## Exploration: Rounded Borders in Dashboard

### Current State

The dashboard uses a cyberpunk/pixel-art aesthetic with the **Press Start 2P** font, where ALL elements should have square borders (no `border-radius`). Two CSS resets already exist:

1. **Universal reset** (style.css line 158-163): `*, *::before, *::after { border-radius: 0; }`
2. **Form element reset** (style.css line 167-169): `button, input, select, textarea { border-radius: 0; }`

Despite these, the **per-page `<select>`** still renders with rounded borders on some browsers.

### Affected Areas

- `src/dashboard/static/style.css` — All CSS definitions (734 lines)
- `src/dashboard/templates/base.html` — Base layout, SVG logo, theme toggle, DATA button
- `src/dashboard/templates/index.html` — Search input, platform select, action buttons, debug checkbox
- `src/dashboard/templates/partials/pagination.html` — Per-page `<select>` (THE PROBLEM ELEMENT)
- `src/dashboard/templates/partials/table.html` — Checkboxes (select-all, per-row)
- `src/dashboard/templates/partials/data_form.html` — Text inputs, textarea
- `src/dashboard/static/script.js` — Dynamic style changes (opacity, display, cursor, width)

### Comprehensive Element-by-Element Analysis

#### Category A: Elements with explicit `border-radius: 0` ✅ (already covered)

| # | Element | CSS Selector / Path | Source |
|---|---------|---------------------|--------|
| 1 | All elements (universal) | `*, *::before, *::after` | style.css:162 |
| 2 | All buttons | `button` | style.css:168 |
| 3 | All text inputs | `input` | style.css:168 |
| 4 | All selects | `select` | style.css:168 |
| 5 | All textareas | `textarea` | style.css:168 |
| 6 | Theme slider track | `.theme-slider` | style.css:111 |
| 7 | Theme slider knob | `.theme-slider::before` | style.css:124 |

#### Category B: Form elements (covered by resets, but native rendering may resist)

**B1. `#search-input` (search box)**
- **Template**: `index.html` line 5 — `<input type="text" id="search-input" class="search-box">`
- **CSS**: `.search-box` (style.css:270) + `input { border-radius: 0; }` + universal reset
- **Risk**: None. Text inputs respect `border-radius: 0` reliably.

**B2. `#platform-select` (multi-select)**
- **Template**: `index.html` line 10 — `<select id="platform-select" class="platform-select" name="platforms" multiple size="1" style="height:34px">`
- **CSS**: `.platform-select` (style.css:137) has `appearance: none;` + inherits `select { border-radius: 0; }`
- **Risk**: **MEDIUM**. The `multiple` attribute changes rendering. Even with `size="1"`, some browsers paint a **listbox**-style widget (not a dropdown), which may use OS-native rounded borders for the scrollbar area or the widget chrome. The `height:34px` inline style combined with `multiple size="1"` is fragile — different browsers render this differently.

**B3. `#per-page-select` (THE PROBLEM ELEMENT)**
- **Template**: `partials/pagination.html` line 19 — `<select id="per-page-select" class="per-page-select" name="per_page">`
- **CSS**: `.per-page-select` (style.css:597) has `-webkit-appearance: none; appearance: none;` + `select { border-radius: 0; }` + universal reset
- **Risk**: **HIGH**. User reports this STILL shows rounded borders. Likely causes:
  - **Browser/OS native rendering**: Some Linux GTK themes and browser engines override `border-radius` on `<select>` elements even with `appearance: none` — the native dropdown button chrome is painted outside CSS control.
  - **Missing `-moz-appearance: none`**: Though modern Firefox supports unprefixed `appearance`, old Firefox (pre-80) requires `-moz-appearance: none`.
  - **CSS cascade**: No specificity issue found — the resets are at the top of the cascade. All `border-radius: 0` rules are present. If the browser still renders rounded, it's a browser/OS-level override, not a CSS cascade problem.
  - **The dropdown popup itself** (the `<option>` list) is OS-rendered and always has rounded corners — this is NOT controllable via CSS.

**B4. `.select-all-cb` and `.job-select` (checkboxes)**
- **Template**: `partials/table.html` lines 4, 19 — `<input type="checkbox" class="select-all-cb">` / `<input type="checkbox" class="job-select">`
- **CSS**: `.select-all-cb, .job-select` (style.css:558) — `accent-color: var(--accent); width: 16px; height: 16px;`
- **Risk**: **MEDIUM**. Native checkboxes with `accent-color` set render as OS-native widgets. On macOS Safari, accent-colored checkboxes have rounded corners. On Linux/Firefox, they may appear rounded or themed by the GTK engine. `border-radius: 0` does NOT apply to native checkbox rendering because checkboxes are **replaced elements** — the CSS border-radius property is ignored for the visual rendering of the native widget.

**B5. `.form-input` elements in data_form (text/email/tel inputs)**
- **Template**: `partials/data_form.html` lines 7, 12, 17, 22 — `<input type="text/email/tel">` with `class="form-input"`
- **CSS**: No explicit `.form-input` CSS rules exist in style.css. Falls through to `input { border-radius: 0; }`.
- **Risk**: Low — regular text inputs respect `border-radius: 0`.

**B6. `.form-textarea` (`#cover-letter`)**
- **Template**: `partials/data_form.html` line 27 — `<textarea id="cover-letter" class="form-input form-textarea">`
- **CSS**: No explicit `.form-textarea` or `.form-input` CSS rules exist. Falls through to `textarea { border-radius: 0; }`.
- **Risk**: Low — textareas respect `border-radius: 0`.

#### Category C: Link/button elements (covered by resets)

**C1. All `.btn` elements** (SCAN, SELECT, AUTO-APPLY, CLEAN DB, DATA)
- **Template**: Various — all `<button class="btn ...">`
- **CSS**: `.btn` (style.css:292) has no border-radius. Covered by `button { border-radius: 0; }`.
- **Risk**: None.

**C2. `.btn-page` (pagination links as `<a>` elements)**
- **Template**: `partials/pagination.html` lines 7, 12 — `<a href="#" class="btn btn-page">`
- **CSS**: `.btn-page` (style.css:360) has no border-radius. Covered by universal reset.
- **Risk**: None.

**C3. `.job-link` (`<a>` elements)**
- **Template**: `partials/table.html` line 27 — `<a href="..." class="job-link">View</a>`
- **CSS**: `.job-link` (style.css:501) has `border: 1px solid var(--accent-dim)` but no border-radius. Covered by universal reset.
- **Risk**: None.

#### Category D: SVG / Graphics

**D1. Logo SVG** (inline in `base.html`)
- **Elements**: `<svg>` with `<text>` children only — NO `<rect>`, `<circle>`, `<ellipse>`, or `<path>` with `rx`/`ry` attributes.
- **Risk**: None. Text rendering in SVG has no border-radius.

**D2. Scan progress bar** (`.scan-progress`, `.progress-track`, `.progress-fill`)
- **Template**: `partials/progress.html` lines 1-5
- **CSS**: `.scan-progress` (style.css:622) — `overflow: hidden` (irrelevant for rounding). No border-radius anywhere on progress elements.
- **Risk**: None.

#### Category E: Structural elements

**E1. `.dashboard-shell`, `.dashboard-header`, `.dashboard-footer`, `.menu-row`, `.pagination-bar`**
- **CSS**: All block-level containers with no border-radius. Covered by universal reset.
- **Risk**: None.

**E2. `.job-table` and its cells**
- **CSS**: `.job-table` (style.css:400) — `border-collapse: collapse` which inherently removes all spacing/border-radius on cells. Table itself has no border-radius.
- **Risk**: None.

#### Category F: JavaScript dynamic styling

**F1. `script.js` inline `style.*` assignments**
- Line 38: `fill.style.width` — progress bar width only
- Lines 107, 110: `btn.style.display` — show/hide debug button
- Lines 162-163, 167-168: `btn.style.opacity`, `btn.style.cursor` — auto-apply button state
- **Risk**: None. No JavaScript sets `border-radius`, `borderRadius`, or any rounding property.

#### Category G: Scrollbar

**G1. `::-webkit-scrollbar-thumb`**
- **CSS**: style.css:706 — `background: var(--border-muted)`. No explicit `border-radius`.
- **Risk**: **LOW-MEDIUM**. WebKit scrollbar thumbs default to rounded corners. The universal `*` selector does NOT reliably apply to WebKit pseudo-elements. Need explicit `border-radius: 0` on `::-webkit-scrollbar-thumb`. However, this is cosmetic/accessory — not a dashboard content element.

#### Category H: HTML structural elements

**H1. Stray `</button>` in `base.html` line 41**
- **Issue**: There's an extra `</button>` closing tag on line 41 after the actual `<button class="btn btn-data">DATA</button>` on line 40. This is **malformed HTML** — the extra closing tag is ignored by the browser (no matching open tag).
- **Risk**: None for border-radius, but it's a markup bug.

### Root Cause Analysis of the `<select>` Problem

The per-page `<select>` (and potentially the platform multi-select) resists `border-radius: 0` because:

1. **Replaced element**: `<select>` is a **replaced element** — the browser paints a native OS widget whose chrome can override CSS. `border-radius: 0` is applied to the CSS box, but the **native widget chrome** (the dropdown arrow button area) is painted by the OS and can have rounded corners.

2. **`appearance: none` is the key** — The user already added it to `.platform-select` and `.per-page-select`. If rounding persists, one possible cause:
   - **Browser cache**: Old CSS is served before the new one loads.
   - **CSS specificity collision**: No collision found — all rules are simple class/type selectors.
   - **The `<select>` dropdown popup**: When you click to open the options list, the popup is entirely OS-rendered and has OS-themed rounded corners. This is NOT controllable via CSS.

3. **For `<select multiple size="1">`**: The `multiple` attribute causes the browser to render a **listbox**, not a dropdown. Even with `size="1"`, some engines use native listbox rendering which ignores `appearance: none`.

### Approaches

1. **Add `appearance: none` to the generic `select` reset** — Currently `appearance: none` is only on `.platform-select` and `.per-page-select`. Moving it to `select { border-radius: 0; appearance: none; -webkit-appearance: none; }` would catch any select that lacks the class.
   - Pros: Catches all selects
   - Cons: Already done per-class and the user reports it doesn't fix the issue
   - Effort: Low

2. **Replace `<select>` with a custom-styled div/button-based widget** — Build the per-page selector with `<div>` + `<button>` + JS, completely avoiding native `<select>` rendering.
   - Pros: Full CSS control over ALL visual aspects including popup
   - Cons: Accessibility impact (keyboard nav, screen readers); more code to maintain
   - Effort: Medium

3. **Add explicit `border-radius: 0` to WebKit scrollbar thumb** — Ensure `::-webkit-scrollbar-thumb { border-radius: 0; }` is added.
   - Pros: Catches a hidden source of rounding
   - Cons: Only affects scrollbar, not the main problem
   - Effort: Low

4. **Replace native checkboxes with custom-styled ones** — Apply `appearance: none; width: 16px; height: 16px; border: 1px solid ...;` to `.select-all-cb, .job-select` to render square custom checkboxes.
   - Pros: Full visual control, pixel-perfect square checkboxes
   - Cons: Need to manage checked/unchecked visual states with `:checked` pseudo-class
   - Effort: Low

5. **Add `-moz-appearance: none` for legacy Firefox compat** — Add the Mozilla-prefixed version alongside the standard `appearance: none`.
   - Pros: Broader browser coverage
   - Cons: Modern Firefox (80+) supports unprefixed; minimal real-world impact
   - Effort: Very low

### Recommendation

**The real problem is a browser/OS level issue**. The CSS already has the correct rules. The investigation reveals:

- **Priority 1**: Verify the fixes are actually being served (hard refresh, cache busting). The universal reset `*, *::before, *::after { border-radius: 0; }` combined with `select { border-radius: 0; }` and `appearance: none` on `.per-page-select` is **technically correct CSS**. If rounding persists, it is almost certainly the **native OS widget chrome** being painted outside CSS control.

- **Priority 2**: Replace the native `<select>` with a custom-styled widget if P1 doesn't resolve it. This is the only way to guarantee 100% control over the visual rendering of dropdown elements.

- **Priority 3**: While in there, fix the native checkboxes too (approach #4), and add the WebKit scrollbar thumb fix (approach #3) for completeness.

### Risks

- Custom dropdown widgets break accessibility if not implemented with ARIA attributes (`role="listbox"`, `aria-expanded`, keyboard navigation).
- The stray `</button>` in `base.html` is harmless but indicates markup quality issue.
- No regression risk — CSS changes only, no functional behavior changes.

### Ready for Proposal

**Yes**. The exploration is complete. Every element in the dashboard has been catalogued:

- **7 elements** already covered (Category A)
- **6 form elements** with varying risk levels (Category B)
- **3 link/button types** with no risk (Category C)
- **2 SVG/graphic groups** with no risk (Category D)
- **2 structural groups** with no risk (Category E)
- **1 JS group** with no risk (Category F)
- **1 scrollbar** with low risk (Category G)
- **1 markup bug** found (Category H)

The orchestrator should tell the user: the CSS resets are already correct. The persisting rounding is most likely a **browser/OS native widget rendering issue** that cannot be fully controlled with CSS alone on `<select>` elements. The next step is a proposal for either (a) accepting this browser limitation, or (b) replacing native form widgets with custom-styled ones for full control.
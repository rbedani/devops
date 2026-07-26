## Exploration: Dino Scan Animation

### Current State

The scan system uses a singleton `ScanState` (`src/dashboard/scan.py`) updated by `run_scan()` via subprocess stdout parsing. The data flow is:

```
run_search.py (stdout PROGRESS: lines)
  → scan.py (parses, updates ScanState singleton)
    → server.py (/scan/status SSE endpoint, yields JSON every 500ms)
      → script.js (EventSource.onmessage → updateProgress() / showDone())
        → DOM: progress.html swapped into #progress-container via HTMX
```

The progress bar is a **3px thin line** (`.scan-progress`) inside a single HTMX-swapped partial (`progress.html` — 5 lines). The scan button is disabled via `disableScanButton()` in JS on scan start, re-enabled via `enableScanButton()` in `showDone()`, and also server-side via `scan_running` Jinja2 context variable.

Theme support: dark/light via `data-theme` attribute, CSS custom properties for all colors (`--accent`, `--text-primary`, `--status-green`, `--status-red`, etc.).

No image assets exist in the project — the logo is an inline SVG in `base.html`.

### Data Flow Diagram

```
[User clicks SCAN]
  │
  ├─► HTMX GET /scan ──► server.py ──► run_scan() (fire-and-forget)
  │                           │
  │                     returns progress.html (initial)
  │                           │
  ├─► HTMX swaps #progress-container
  │
  ├─► script.js: startScanListener()
  │       │
  │       ├─► new EventSource('/scan/status')
  │       │
  │       ├─► onmessage: JSON { pct, target, completed, total, log, done }
  │       │       │
  │       │       ├─► done=false → updateProgress(data) → fill.style.width = pct%
  │       │       └─► done=true  → showDone(data) → replace innerHTML with green/red bar
  │       │
  │       └─► onerror: retry, timeout after 10s, re-enable button
  │
  └─► SSE loop: server.py yields {pct, done} every 500ms
                      until scan_state.running=False
```

### How the Dino Animation Would Hook Into the SSE Pipeline

The Dino canvas replaces the simple `updateProgress()` call. The SSE `onmessage` handler would:

1. Receive the same `{pct, done, error, ...}` JSON
2. Pass `data.pct` to a Dino renderer class
3. The renderer runs a `requestAnimationFrame` loop that:
   - Maps `data.pct` (0–100) to Dino x-position across the 45px banner
   - Animates the Dino's running legs (frame cycling)
   - Spawns obstacles at configurable progress thresholds (cactus at 25%, pterodactyl at 50%, etc.)
   - Detects obstacle proximity and triggers jump/dodge animation
4. On `done=true`:
   - Plays a completion animation (Dino stops, T-Rex roar pose)
   - Transitions the banner back to 3px (green for success, red for error)

### Files Affected

| File | Change Description |
|------|--------------------|
| `src/dashboard/templates/partials/progress.html` | Expand from 3 `.scan-progress` div to include a `<canvas>` element + banner container. Add collapse transition on completion. |
| `src/dashboard/static/style.css` | Add Dino banner styles (~45px height), transition from 3px→45px→3px, canvas sizing, scanning animation state. |
| `src/dashboard/static/script.js` | Add `DinoCanvasRenderer` class: canvas setup, pixel-art sprite data (running frames, jump, obstacles), render loop, progress syncing, `showDone()` integration. |
| `src/dashboard/server.py` (optional) | Increase SSE frequency or add richer state fields for smoother animation. |
| `tests/unit/test_dashboard_backend.py` | Add frontend tests for Dino rendering, canvas element presence, progress syncing, completion state. |

### Technical Approach

**Recommended: Canvas 2D overlay**

A `<canvas>` element sits inside `#progress-container`. On scan start, the container expands from 3px to **45px** via CSS transition. A `DinoCanvasRenderer` JS class manages:

1. **Canvas setup**: 2D drawing context, pixel ratio handling, clear on each frame
2. **Sprite data**: 2D arrays (0/1) for each animation frame — running legs (2-3 frames), jump pose, idle/roar pose, cactus obstacle, pterodactyl obstacle
3. **Render loop**: `requestAnimationFrame` + interpolation between last-known SSE `pct` values for smooth movement
4. **Progress sync**: Dino x-position = `(pct / 100) * canvasWidth`. Obstacles spawn at fixed thresholds.
5. **Theme awareness**: On init, read `getComputedStyle(document.documentElement)` to extract `--accent`, `--text-primary`, `--status-green`, `--status-red` for pixel colors
6. **Completion**: On `done=true`, set Dino to idle/roar pose, hold 500ms, then CSS transition collapses canvas to 3px success/error bar

**Why Canvas over alternatives:**

| Criterion | Canvas | CSS box-shadow | SVG |
|-----------|--------|----------------|-----|
| Maintainability | Sprite as 2D arrays | 50+ box-shadow vals/frame | Inline SVG paths |
| Dynamic obstacles | Trivial (draw at x,y) | Very hard | Possible |
| Performance | Good (small viewport) | OK (many shadows) | Good |
| Pixel art aesthetic | ✓ (fillRect) | ✓ (inherently pixel) | ✓ (crispEdges) |
| No external deps | ✓ | ✓ | ✓ |

### Key Risks

1. **Canvas focus/tab pause**: `requestAnimationFrame` pauses when tab is backgrounded — Dino freezes, resumes when tab is active. Acceptable behavior, but users should see it resume correctly.
2. **SSE granularity**: Current SSE emits every 500ms — a running animation at 500ms intervals would be jerky. Solution: interpolation between SSE updates via `requestAnimationFrame` time delta (estimate position between last two known pct values).
3. **Theme color extraction**: Must read CSS custom properties via JS at init time (not hardcoded) to support dark/light theme. If theme changes mid-scan, must re-read colors.
4. **Transition height conflict**: CSS `transition: height 0.3s` for the banner expand/collapse could conflict with JS canvas updates. Must carefully sequence: expand canvas first, THEN start animation loop. On completion: stop loop first, THEN collapse.
5. **Touch/mobile**: The 45px banner must not interfere with touch targets (scan button, etc.). Ensure `pointer-events: none` on the canvas during animation.

### Size Estimate

| Layer | Lines |
|-------|-------|
| CSS (banner, transitions, canvas) | ~60 |
| JS (DinoCanvasRenderer, sprite data, loop, obstacles) | ~200 |
| HTML (progress.html rewrite) | ~15 |
| Server (optional SSE tweaks) | ~5 |
| Tests | ~60 |
| **Total** | **~340** |

### Ready for Proposal

**Yes** — the architecture, data flow, and approach are well understood. The orchestrator can proceed to `sdd-propose` with the Canvas 2D approach.
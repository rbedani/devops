# Tasks: Dino Scan Animation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~415 (60 + 15 + 200 + 80 + 60) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr-default |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Full dino animation (CSS + HTML + JS + tests) | PR 1 | `pytest tests/unit/ -v --tb=short` | Start scan, observe canvas rendering | git revert of 4 files |

## Phase 1: Foundation — CSS & HTML

- [x] 1.1 CSS: Add `.scan-progress.expanded` state (45px height, transition 300ms), canvas positioning (absolute, full-width, pointer-events: none), mobile 35px at ≤768px — `src/dashboard/static/style.css`
- [x] 1.2 HTML: Add `<canvas id="dino-canvas">` inside `#progress-container` before existing `.scan-progress` — `src/dashboard/templates/partials/progress.html`

## Phase 2: Core Implementation — JS Rendering

- [x] 2.1 JS: `DinoCanvasRenderer` class — constructor reads canvas context + CSS vars, defines pixel sprites (dino run1/run2, jump, success, dead, cactus-sm, cactus-lg, pterodactyl as 2D `number[][]`), `_drawSprite(sprite, x, y)` blits at 2x pixel scale — `src/dashboard/static/script.js`
- [x] 2.2 JS: `start()`, `stop(success)`, `resize()`, `_readThemeColors()` (getComputedStyle from banner), `updateProgress(pct)` — `src/dashboard/static/script.js`
- [x] 2.3 JS: `_loop(timestamp)` — rAF callback interpolates currentPct toward targetPct, positions dino linearly, spawns obstacles at 25/40/50/65/75% thresholds, auto-jump when dino approaches obstacle — `src/dashboard/static/script.js`
- [x] 2.4 JS: Wire into `startScanListener()` — on `data.pct` call `dino.updateProgress(pct)`, on `data.done` call `dino.stop(!data.error)` with 1.5s collapse delay — `src/dashboard/static/script.js`

## Phase 3: Testing

- [x] 3.1 Test: `DinoCanvasRenderer` init creates context and reads CSS vars — `tests/unit/test_dino_animation.py`
- [x] 3.2 Test: pixel sprites array is defined and non-empty for all 7 frames — `tests/unit/test_dino_animation.py`
- [x] 3.3 Test: `updateProgress(pct)` via source inspection — `tests/unit/test_dino_animation.py`
- [x] 3.4 Test: `stop(true)` success pose and `stop(false)` dead pose via source inspection — `tests/unit/test_dino_animation.py`
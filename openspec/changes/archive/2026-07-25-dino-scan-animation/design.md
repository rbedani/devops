# Design: Dino Scan Animation

## Technical Approach

Overlay a `<canvas>` element inside `#progress-container` positioned absolutely above the existing 3px progress bar. A `DinoCanvasRenderer` class manages the `requestAnimationFrame` loop that interpolates between SSE `pct` values using time deltas. Pixel sprites are 2D arrays of 0/1 drawn at 2×2 CSS-pixel scale with colors read from CSS custom properties. No external assets, no backend changes.

## Architecture Decisions

### Decision: Canvas overlay vs. full-replacement render

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Canvas overlays progress bar absolutely | Progress bar stays visible below; SSE position sync is independent | **Selected** |
| Replace progress bar with canvas entirely | Lose the neon fill visualization; more complex layout reset | Rejected |

### Decision: Sprite definition format

| Option | Tradeoff | Decision |
|--------|----------|----------|
| 2D arrays of 0/1 per frame | Self-contained, zero network, trivially composable | **Selected** |
| Single pixel-art image with sprite-sheet crop | Needs image load timing, CORS issues with local dev | Rejected |

### Decision: Obstacle timing strategy

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Fixed thresholds (25%, 50%, 75% cactus; 40%, 65% pterodactyl) + auto-jump in 10% window | Deterministic, testable; dino always avoids obstacles | **Selected** |
| Random distribution within ranges | Fun but less predictable, harder to verify | Rejected |

### Decision: Theme color re-read timing

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Read `getComputedStyle` on every SSE message | ~0.02ms per call; catches mid-scan theme switches | **Selected** |
| Read once at init | Simpler but stale colors if theme changes mid-scan | Rejected |

### Decision: SSE frequency

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Keep 500ms for backend, interpolate via rAF client-side | No backend change, rAF handles smooth motion between ticks | **Selected** |
| Change to 250ms on backend | Smoother position but unnecessary with rAF interpolation | Rejected |

## Data Flow

```
[scan.py] ScanState.progress_pct
    ↓ (every 500ms)
[server.py] SSE event {pct, done, error}
    ↓ (EventSource onmessage)
[script.js] DinoCanvasRenderer.updateProgress(data.pct)
    ↓ (stores targetPct, rAF loop interpolates)
[DinoCanvasRenderer._loop] currentPct → currentPct
    ↓
    ┌─ Draw ground line at y = bannerHeight - 6
    ├─ Draw obstacles at positions mapped from currentPct
    ├─ Draw dino frame at x = map(currentPct, 0→100, padding→canvasWidth-dinoWidth-20)
    └─ requestAnimationFrame(_loop)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/dashboard/static/style.css` | Modify | +35 lines: `#progress-container.scan-active` transition, canvas positioning, mobile 35px |
| `src/dashboard/static/script.js` | Modify | +250 lines: `DinoCanvasRenderer` class, sprites, render loop, SSE integration |
| `src/dashboard/templates/partials/progress.html` | Modify | +2 lines: add `<canvas>` element inside scanner container |
| `src/dashboard/server.py` | Modify (optional) | +1 line: reduce SSE sleep to 250ms for smoother updates |
| `src/dashboard/scan.py` | No change | ScanState data contract remains unchanged |
| `tests/unit/test_dashboard_frontend.py` | Create | ~80 lines: canvas init test, rendered sprite pixel tests, lifecycle transitions |

No new files created — all changes are in-place modifications.

## Interfaces / Contracts

```python
# ScanState (unchanged — consumed as-is)
# SSE event payload (unchanged — consumed as-is):
#   { "pct": float, "done": bool, "error": str | None }

# DinoCanvasRenderer (new class, script.js)
class DinoCanvasRenderer {
    constructor(canvas: HTMLCanvasElement, container: HTMLElement)
    updateProgress(pct: number): void       // set targetPct from SSE
    start(): void                           // begin rAF loop
    stop(success: boolean): void            // end loop, draw final pose, trigger collapse
    resize(): void                          // match container size, handle DPR
    
    // Private
    _loop(timestamp: DOMHighResTimeStamp): void
    _drawFrame(sprite: number[][], x: number, y: number): void
    _readThemeColors(): { body: string, eye: string, ground: string }
}
```

### Sprite Layout

Each sprite is `number[][]` where `0` = transparent, `1` = fill color. Pixel scale is 2×2 CSS pixels via `ctx.scale(2, 2)` with `imageSmoothingEnabled = false`.

- **Dino body**: ~10×10 pixel grid (20×20 CSS px at 2×)
- **Cactus**: 4×8 pixel grid (8×16 CSS px)
- **Pterodactyl**: 8×4 pixel grid (16×8 CSS px)
- **Ground line**: single row of `1`s across full canvas width

Frames: `run1`, `run2`, `jump`, `success`, `dead`

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (JS) | `DinoCanvasRenderer` init, `_readThemeColors` returns CSS vars, sprite matrices not empty | jsdom + canvas mock in Node |
| Unit (JS) | `updateProgress` sets `targetPct` correctly, interpolation math | Pure function tests |
| Unit (PY) | `progress.html` renders `<canvas>` when scan active | Jinja2 TemplateResponse, assert `<canvas>` in output |
| Integration | SSE flow: canvas init triggered on scan start | FastAPI TestClient + mocked scan, check DOM returned |
| Visual | Correct pixel colors in dark/light themes | Headless Playwright screenshot comparison |
| Visual | Obstacle timing: dino jumps at 25%, 50%, 75% | Frame-by-frame pixel assertion in Playwright |

**Note**: Pure JS canvas rendering is hard to unit-test in a Python test suite. The approach is to test the *integration boundary* (that the template includes the canvas and the JS module exports the expected API) and rely on Playwright E2E for visual correctness. Unit tests for the sprite matrices and interpolation logic should be added if a JS test runner is introduced.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. This is purely a client-side visual enhancement.

## Migration / Rollout

No migration required. The animation is stateless — it activates on the next `/scan` request and requires no data migration. Rollback is a git revert of the 4 modified files.

## Open Questions

- [ ] Should SSE interval be reduced to 250ms for smoother motion? The proposal marks this optional. Current 500ms + rAF interpolation should be smooth enough; test first, reduce if needed.
- [ ] Add a JS test runner (vitest/Playwright) or rely on integration-level DOM assertions + manual visual verification? The existing test framework is pytest-only.
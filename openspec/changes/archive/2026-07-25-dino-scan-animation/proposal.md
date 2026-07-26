# Proposal: Dino Scan Animation

## Intent

Add a Chrome Dino-style pixel running animation to the scan progress bar — zero business value, pure delight. Reinforces the retro arcade aesthetic of JOB DASHBOARD and makes scan wait time feel alive.

## Scope

### In Scope

- Expand progress container from 3px to ~45px banner during active scan with CSS transition
- Canvas-based pixel-art Dino running left to right, synced to SSE `pct` values
- Obstacles: cactus (ground) at 25%/60%, pterodactyl (air) at 40%/80% progress thresholds
- Dino jump animation auto-triggered by obstacle proximity (no user input)
- On 100%: dino stops, banner collapses to 3px green/red bar with completion pose
- Dark/light theme color extraction via `getComputedStyle()` on init
- Mobile: `pointer-events: none`, no touch interference with scan button

### Out of Scope

- NO interactive gameplay (no user controls, no score, no game loop)
- NO external image or sprite assets (all pixel art via 2D arrays of 0/1)
- NO backend changes unless trivial SSE timing improvement (optional)
- NO breaking existing scan, SSE, or progress flow

## Capabilities

### New Capabilities

None. No new spec-level behavior boundaries introduced.

### Modified Capabilities

- `dashboard-viewer` → Execute Scan: progress bar animation enhanced from static 3px fill to Dino pixel animation banner. Spec delta adds animation behavior requirements (expand, run, obstacles, collapse).

## Approach

Canvas 2D overlay inside `#progress-container`. `DinoCanvasRenderer` JS class manages a `requestAnimationFrame` loop that interpolates between SSE `pct` updates via time-delta. Pixel sprites defined as 2D arrays of 0/1 (no external assets). On scan start, container expands 3px→45px via CSS transition; on completion, reverses after 500ms hold.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/dashboard/static/style.css` | Modified | ~60 lines: banner height, transitions, canvas sizing, scanning animation state |
| `src/dashboard/static/script.js` | Modified | ~200 lines: `DinoCanvasRenderer` class, sprite data, render loop, progress sync |
| `src/dashboard/templates/partials/progress.html` | Modified | ~15 lines: expand from 3px div to include `<canvas>` + banner container |
| `src/dashboard/server.py` | Optional | ~5 lines: increase SSE frequency from 500ms to 250ms for smoother interpolation |
| `openspec/changes/dino-scan-animation/specs/dashboard-viewer/spec.md` | New | Delta spec for progress animation requirements |
| `tests/unit/test_dashboard_backend.py` | Modified | ~60 lines: tests for canvas element, Dino rendering states, completion flow |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| rAF pauses on tab background → Dino freezes, resumes incorrectly | Medium | Interpolation recalculates position from last known pct on resume; no data loss |
| Theme changes mid-scan → wrong colors | Low | Re-read CSS vars on each SSE message (cheap, single getComputedStyle call) |
| CSS height transition conflicts with canvas resize | Medium | Sequence: expand canvas first, THEN start animation; on done, stop loop THEN collapse |

## Rollback Plan

Revert the 4 affected files (`style.css`, `script.js`, `progress.html`, `server.py`) to their pre-commit state. The progress bar returns to the current 3px static bar with no animation — no data loss, no broken scans.

## Dependencies

None.

## Success Criteria

- [ ] Scan starts → progress container expands to 45px with Dino visible and running LTR
- [ ] Dino sprite animates (legs cycle) during active scan
- [ ] Obstacles appear at configured thresholds and Dino jump animation triggers
- [ ] On scan complete → banner collapses to 3px (green on success, red on error)
- [ ] Dark and light themes both show correct pixel colors
- [ ] Mobile: canvas does not intercept touch events on scan button
- [ ] All existing scan/SSE/progress tests still pass
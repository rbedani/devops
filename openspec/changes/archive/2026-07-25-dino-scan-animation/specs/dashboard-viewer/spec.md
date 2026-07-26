# Delta for dashboard-viewer

## ADDED Requirements

### Requirement: Dino Scan Animation

When a scan runs, the progress bar SHALL display a Chrome Dino-style pixel animation. The system MUST meet the following sub-requirements:

#### Animation State Lifecycle

- **Expanded**: On scan start, `#progress-container` MUST expand from 3px to 45px height via CSS transition (~300ms). The original 3px fill bar SHALL remain visible inside the banner.
- **Collapsed**: On scan completion or error, the banner MUST collapse back to 3px after a 1.5s delay.

#### Dino Pixel Sprites

Animation SHALL use programmatic pixel sprites (2D arrays of 0/1) on Canvas 2D with minimum 4 frames: running1, running2, jumping, and dead/success pose. Pixel size SHALL be 2×2 CSS pixels. Colors MUST derive from CSS custom properties (`--accent` for body, `--text-primary` for eyes).

#### Obstacles

Cactus (ground) MUST appear at ~25%, ~50%, ~75% progress. Pterodactyl (air) MUST appear at ~40% and ~65%. Dino SHALL perform a jump animation timed to cactus approach, and an avoid animation for pterodactyl.

#### Progress Synchronization

Dino x-position MUST map linearly to scan progress percentage. Between SSE updates (every 500ms), the animation SHALL interpolate via `requestAnimationFrame` time delta. At 100%, Dino SHALL stop in success pose (dead pose on error). The underlying 3px fill bar MUST mirror the same percentage.

#### Theme Awareness

Canvas colors MUST read `--accent`, `--text-primary`, `--bg-secondary` from CSS custom properties. Colors SHALL be re-read on each SSE message. Dark and light themes MUST both appear correct.

#### Mobile Safety

Canvas area MUST have `pointer-events: none`. On viewport ≤768px, banner height SHALL be 35px instead of 45px.

#### Scenario: Scan starts with running Dino

- GIVEN the dashboard is idle with a collapsed progress bar
- WHEN Execute Scan starts and SSE sends `pct > 0`
- THEN `#progress-container` expands to animation height with Dino running LTR

#### Scenario: Obstacle triggers

- GIVEN a scan is running with Dino visible
- WHEN progress reaches ~25%
- THEN cactus appears at ground level and Dino performs jump animation

#### Scenario: Completion collapses banner

- GIVEN progress reaches 100%
- WHEN the final SSE event fires
- THEN Dino stops in success pose; after 1.5s delay banner collapses to 3px with green fill bar

#### Scenario: Error shows dead pose

- GIVEN a scan encounters an error
- WHEN SSE sends an error event
- THEN Dino stops in dead pose; after 1.5s delay banner collapses to 3px with red fill bar

#### Scenario: Theme switch mid-scan

- GIVEN a scan is running in light theme
- WHEN the theme switches to dark (CSS custom properties change)
- THEN on the next SSE event, Dino colors update to match the new theme

#### Scenario: Mobile touch passes through

- GIVEN a viewport ≤768px
- WHEN user taps Execute Scan during an animation
- THEN the button click registers; the canvas does not intercept the event

#### Scenario: Tab backgrounding resumes safely

- GIVEN a scan is running and the tab is backgrounded
- WHEN the tab returns to foreground
- THEN Dino position recalculates from the last known `pct` value

## MODIFIED Requirements

### Requirement: Execute Scan

MUST start async scrape with cyberpunk progress bar featuring Dino pixel animation. On completion, table repopulates.
(Previously: static 3px progress bar without animation)

#### Scenario: Scan populates table (unchanged)

- GIVEN empty DB
- WHEN Execute Scan completes
- THEN table shows new results
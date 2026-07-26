# Dashboard Viewer Specification

## Purpose

Interactive web dashboard for browsing, searching, and managing scraped job listings without CLI access. Zero changes to existing `src/` modules.

## Requirements

### Requirement: Dashboard Server

MUST serve FastAPI + HTMX + Jinja2. Port configurable via `DASHBOARD_PORT` (default `8080`). SHALL serve static assets and HTMX partials.

#### Scenario: Configured port

- GIVEN `DASHBOARD_PORT=9090`
- WHEN the server starts
- THEN it listens on port 9090

#### Scenario: Dashboard page

- GIVEN the server is running
- WHEN GET `/`
- THEN full HTML page with all job columns

### Requirement: Job Table

MUST display 9 columns: date_published, platform, title, company, modality, salary, location, link, status. Status SHALL show `auto-applied`, `manual_intervention`, `expired`, or an error string.

#### Scenario: All columns render

- GIVEN 3 job listings in DB
- WHEN the dashboard loads
- THEN all 3 rows display across 9 columns

#### Scenario: Status value

- GIVEN a job with status `auto-applied`
- WHEN the table renders
- THEN status cell shows `auto-applied`

### Requirement: Pagination

MUST support Previous/Next. Per-page: 10, 50, 100, 250, All. MUST persist through search filters.

#### Scenario: Next page

- GIVEN 25 jobs at 10/page
- WHEN user clicks Next
- THEN page 2 shows rows 11–20

#### Scenario: All per page

- GIVEN 150 jobs
- WHEN user selects "All"
- THEN all 150 rows render

### Requirement: Header Menu

The header menu MUST include search (title/company), Execute Scan, Select toggle, DATA (toggle for the DATA panel), Auto-Apply stub. Auto-Apply SHALL log only; MUST NOT submit.

#### Scenario: Search filter

- GIVEN jobs "Engineer" and "Designer"
- WHEN user types "Engineer"
- THEN only matching rows shown

#### Scenario: Auto-Apply stub

- GIVEN user clicks Auto-Apply
- WHEN handler fires
- THEN log written; no application submitted

#### Scenario: DATA toggle shows/hides panel

- GIVEN the DATA panel is hidden
- WHEN the user clicks the DATA button in the header
- THEN the DATA panel slides in with the dynamic form, SAVE, and ADD FIELD buttons
- AND clicking DATA again hides the panel

### Requirement: Select / Checkbox

Checkbox column hidden by default. Toggle shows it at table start. Header checkbox selects/deselects all visible rows.

#### Scenario: Header selects all

- GIVEN Select ON, 25 rows visible
- WHEN header checkbox checked
- THEN all 25 rows checked

### Requirement: Execute Scan

MUST start async scrape with cyberpunk progress bar featuring Dino pixel animation. On completion, table repopulates.

#### Scenario: Scan populates table

- GIVEN empty DB
- WHEN Execute Scan completes
- THEN table shows new results

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

### Requirement: Debug Mode

MUST limit scan to 2 results per scraper. Visible only in non-production.

#### Scenario: Debug limits

- GIVEN debug enabled, 100 jobs expected
- WHEN scan runs
- THEN ≤2 results per scraper persisted

#### Scenario: Hidden in production

- GIVEN production environment
- WHEN dashboard renders
- THEN debug checkbox absent

### Requirement: Cyberpunk Theme

MUST use dark bg, purple (`#a855f7`) and cyan (`#22d3ee`) accents, flat 1px solid borders, monospace data cells. All `border-radius`, `box-shadow`, `text-shadow`, and gradient backgrounds are set to zero/removed.

#### Scenario: Theme applied

- GIVEN dashboard loaded
- WHEN browser renders
- THEN CSS variables apply cyberpunk palette; all corners are flat (border-radius: 0)

### Requirement: Status Migration

MUST add `status` column via `ALTER TABLE ... ADD COLUMN`. MUST NOT drop or alter existing columns.

#### Scenario: Additive migration

- GIVEN DB without `status` column
- WHEN dashboard starts
- THEN column added; existing data preserved

### Requirement: Debug Stop Button

When debug mode is active AND a scan is running, the progress area MUST display a STOP button. Clicking it MUST terminate the running scan subprocess and reset state to idle.

The system MUST send SIGTERM to the subprocess on stop. If the subprocess does not exit within 500ms, the system MUST escalate to SIGKILL. After termination, the system MUST close the SSE stream, re-enable the SCAN button, and collapse the progress banner. The stop button MUST NOT be visible when debug mode is off or when no scan is running.

#### Scenario: Stop mid-scan

- GIVEN debug mode is ON and a scan is running (progress visible, SSE active)
- WHEN the user clicks the STOP button
- THEN the subprocess receives SIGTERM and terminates
- AND progress collapses, SSE closes, SCAN button re-enables
- AND newly added rows (from already-completed platforms) remain in the table

#### Scenario: Stop after scan naturally completes

- GIVEN debug mode is ON and a scan finishes just as the user clicks STOP
- WHEN the cancel event is set on an already-exited subprocess
- THEN the system MUST NOT raise an error (idempotent kill)
- AND the scan progresses normally to completion state

#### Scenario: Subprocess ignores SIGTERM

- GIVEN a stuck subprocess that does not respond to SIGTERM
- WHEN the user clicks STOP
- THEN after 500ms the system sends SIGKILL
- AND the subprocess terminates, SSE closes, progress collapses

### Requirement: Date Filter

The table header SHALL include a date filter dropdown with options: `Any date`, `Last 24h`, `Last week`, `Last month`. Selecting an option MUST add a `since` query parameter to GET /table (`since=24h`, `since=7d`, `since=30d`). The server MUST filter `scraped_at` using the corresponding timedelta. The filter MUST be preserved through pagination.

#### Scenario: Filter last 24h

- GIVEN 10 jobs from last week and 2 from the last hour
- WHEN the user selects "Last 24h"
- THEN the table shows only the 2 recent jobs

#### Scenario: Filter resets to Any date

- GIVEN a "Last month" filter is active
- WHEN the user selects "Any date"
- THEN all jobs are shown with no time restriction

### Requirement: Content Dedup Hash

The `jobs` table MUST gain a `content_hash` column storing SHA-256 of `title + company + description`. The upsert SHALL include `ON CONFLICT(content_hash) DO UPDATE` alongside the existing URL constraint. A duplicate job with identical content but a different URL SHALL be rejected.

The table SHALL display the first 8 hex chars of the content hash in a new "Hash" column (between "link" and "status").

#### Scenario: Duplicate content rejected

- GIVEN a job "Engineer at Acme" exists with hash `a1b2c3d4...`
- WHEN the scraper returns "Engineer at Acme" from a different URL
- THEN the job is NOT inserted and the existing row's URL is updated

#### Scenario: Unique content inserted

- GIVEN no job with hash `x1y2z3...` exists
- WHEN the scraper returns a new job
- THEN the job is inserted normally

### Requirement: DATA Panel — SAVE and ADD FIELD Buttons

The DATA panel form header MUST contain a SAVE button and an ADD FIELD button. SAVE SHALL send an HTMX POST to persist all current fields. ADD FIELD SHALL append a new empty field row via HTMX GET of a field template partial. Both buttons SHALL be disabled during an active save or add operation to prevent double-submission.

#### Scenario: SAVE persists fields

- GIVEN two fields are filled in the DATA panel
- WHEN the user clicks SAVE
- THEN an HTMX POST sends all field data to the server
- AND the server persists to `profile_fields` and returns a success indicator

#### Scenario: ADD FIELD inserts new row

- GIVEN the DATA panel shows 2 fields
- WHEN the user clicks ADD FIELD and selects type `text`
- THEN a third field row appears
- AND the existing field values are preserved
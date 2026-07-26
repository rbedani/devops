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

MUST include search (title/company), Execute Scan, Select toggle, Auto-Apply stub. Auto-Apply SHALL log only; MUST NOT submit.

#### Scenario: Search filter

- GIVEN jobs "Engineer" and "Designer"
- WHEN user types "Engineer"
- THEN only matching rows shown

#### Scenario: Auto-Apply stub

- GIVEN user clicks Auto-Apply
- WHEN handler fires
- THEN log written; no application submitted

### Requirement: Select / Checkbox

Checkbox column hidden by default. Toggle shows it at table start. Header checkbox selects/deselects all visible rows.

#### Scenario: Header selects all

- GIVEN Select ON, 25 rows visible
- WHEN header checkbox checked
- THEN all 25 rows checked

### Requirement: Execute Scan

MUST start async scrape with cyberpunk progress bar. On completion, table repopulates.

#### Scenario: Scan populates table

- GIVEN empty DB
- WHEN Execute Scan completes
- THEN table shows new results

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

MUST use dark bg, purple (`#a855f7`) and cyan (`#22d3ee`) accents, glowy `box-shadow` borders, monospace data cells.

#### Scenario: Theme applied

- GIVEN dashboard loaded
- WHEN browser renders
- THEN CSS variables apply cyberpunk palette

### Requirement: Status Migration

MUST add `status` column via `ALTER TABLE ... ADD COLUMN`. MUST NOT drop or alter existing columns.

#### Scenario: Additive migration

- GIVEN DB without `status` column
- WHEN dashboard starts
- THEN column added; existing data preserved
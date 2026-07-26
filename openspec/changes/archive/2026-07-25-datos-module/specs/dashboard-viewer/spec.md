# Delta for dashboard-viewer

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Header Menu

The header menu MUST include search (title/company), Execute Scan, Select toggle, DATA (toggle for the DATA panel), Auto-Apply stub. Auto-Apply SHALL log only; MUST NOT submit.
(Previously: No DATA button in header menu — DATA was not a toggled panel)

#### Scenario: DATA toggle shows/hides panel

- GIVEN the DATA panel is hidden
- WHEN the user clicks the DATA button in the header
- THEN the DATA panel slides in with the dynamic form, SAVE, and ADD FIELD buttons
- AND clicking DATA again hides the panel

*(Existing Auto-Apply stub scenario and Search filter scenario remain unchanged — see main spec.)*

## REMOVED Requirements

None.

## RENAMED Requirements

None.
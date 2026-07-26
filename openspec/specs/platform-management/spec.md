# Platform Management Specification

## Purpose

Manage scan platform configurations (name + URL) that the scraper module uses to discover job listings. Supports listing, adding, and removing platforms via the dashboard UI. LinkedIn is pre-configured.

## Requirements

### Requirement: Platform Registry

The system MUST maintain a `scan_platforms` SQLite table seeded with LinkedIn (`https://www.linkedin.com/jobs/`). Each platform SHALL have a name (unique, max 64 chars) and a URL (valid HTTP/HTTPS, max 512 chars).

The system SHALL expose a GET endpoint returning all platforms as a list. Each entry SHALL display the platform name and its URL.

#### Scenario: Default platform on first load

- GIVEN an empty `scan_platforms` table
- WHEN the dashboard platform management panel loads
- THEN "LinkedIn" is shown with its URL

#### Scenario: List multiple platforms

- GIVEN platforms "LinkedIn" and "InfoJobs" exist
- WHEN the user opens the platform list
- THEN both names and URLs appear sorted alphabetically

### Requirement: Add Platform

A form with name and URL fields MUST allow adding a new platform. An empty name or invalid URL SHALL be rejected. A duplicate name SHALL be rejected with "Platform already exists".

On success, the platform SHALL appear immediately in the list via HTMX swap.

#### Scenario: Add valid platform

- GIVEN the platform list shows only "LinkedIn"
- WHEN the user enters name "InfoJobs" and URL "https://www.infojobs.net/" and clicks Add
- THEN "InfoJobs" appears in the list with its URL

#### Scenario: Add duplicate name

- GIVEN "LinkedIn" already exists
- WHEN the user enters name "LinkedIn" with any URL
- THEN the system rejects with "Platform already exists"

#### Scenario: Invalid URL

- GIVEN the add form is visible
- WHEN the user enters name "Test" with URL "not-a-url"
- THEN the system rejects with "Invalid URL format"

### Requirement: Remove Platform

A remove button next to each platform MUST delete it from the table. Confirmation SHALL be required. LinkedIn MAY be removed (user choice). After removal, the platform SHALL disappear from the list.

#### Scenario: Remove a platform

- GIVEN platforms "LinkedIn" and "InfoJobs" exist
- WHEN the user clicks Remove on InfoJobs and confirms
- THEN InfoJobs is deleted and the list shows only LinkedIn

#### Scenario: Remove all platforms

- GIVEN only "LinkedIn" exists
- WHEN the user removes LinkedIn
- THEN the platform list is empty
- AND no platforms are available for scan selection

### Requirement: Scan Integration

Platforms managed here SHALL be offered as selectable targets in the Execute Scan flow. The scan module MUST read `scan_platforms` to determine which sites to scrape. Removing a platform SHALL exclude it from future scans.

#### Scenario: Platform available for scan

- GIVEN "InfoJobs" exists in `scan_platforms`
- WHEN the user opens the scan configuration
- THEN InfoJobs appears as a selectable platform in the platform-select dropdown
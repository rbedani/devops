# Delta for Data Profile — Visual Alignment

## MODIFIED Requirements

### Requirement: Dynamic Form Fields

The system MUST render a list of user-defined fields. Each field SHALL have a name (free text, max 100 chars) and a type selected from: `numeric`, `alphanumeric`, `date`, `datetime`, `text`, `email`, `phone`, `url`, `file`.

An ADD FIELD button MUST insert a new empty row into the form. The system SHALL support an arbitrary number of fields. On save, the system MUST persist all fields to a `profile_fields` SQLite table.

Each field row MUST use these CSS classes: `.datos-field-row` (container), `.datos-form-group` + `.datos-form-label` (label wrapper), `.datos-form-select` (type dropdown), `.datos-form-input` (name/value inputs). The ADD FIELD button MUST use `.btn.btn-toggle`. The REMOVE button MUST use `.btn.btn-remove-field` (red outline, unchanged).

(Previously: field rows used non-matching classes `data-field-row`, `field-type-select`, `field-name-input`, `field-value-input`; ADD FIELD used hardcoded accent fallback)

#### Scenario: Add and fill a field

- GIVEN an empty data form
- WHEN the user clicks ADD FIELD and selects type `email` with name "Work Email"
- THEN a new form row appears with `.datos-form-select`, `.datos-form-input`, and `.datos-form-label` elements
- AND the field is persisted to `profile_fields` after SAVE

#### Scenario: Remove a field

- GIVEN a saved field "Phone" with type `phone`
- WHEN the user clicks the remove button (`.btn.btn-remove-field`) on that row
- THEN the field is deleted from `profile_fields` and the row disappears

### Requirement: SAVE Persistence

A SAVE button MUST persist ALL visible fields in a single transaction. On success, the system SHALL show a confirmation toast. On failure (e.g., DB error), the system SHALL show an error message and NOT lose previously saved data.

The toolbar containing the SAVE and ADD FIELD buttons MUST use a `.menu-row` wrapper (`.bg-secondary`, `border: 1px solid var(--border-muted)`, `height: 36px` button targets). The SAVE button MUST use `.btn.btn-scan` (solid accent fill). No `<hr>` dividers SHALL appear between panel sections — instead, section containers SHALL use `border-bottom`.

(Previously: toolbar used bare `.data-panel-header` div, SAVE used `var(--accent2, #22d3ee)` outline with no semantic anchor, `<hr>` elements separated sections)

#### Scenario: Save all fields

- GIVEN fields "Name" (alphanumeric) and "Age" (numeric) with values entered
- WHEN the user clicks SAVE (`.btn.btn-scan`)
- THEN both fields are persisted to `profile_fields` and a success toast appears

#### Scenario: Save with validation failure

- GIVEN a field "Age" with type `numeric` containing text "abc"
- WHEN the user clicks SAVE (`.btn.btn-scan`)
- THEN the save is rejected and no fields are persisted
- AND the Age field shows a validation error

### Requirement: CV Upload

The system MUST accept PDF files for upload. Non-PDF files SHALL be rejected with a user-facing error. On upload, the system SHALL store the file at `data/cv/{filename}.pdf` and save the path (plus upload date) in a `cv_files` SQLite table.

A preview link MUST display after upload. A delete button SHALL remove the file from disk and the DB row.

The CV zone MUST use `border: 2px solid var(--border-muted)` (solid, not dashed), transitioning to `var(--accent)` on hover. The UPLOAD button MUST use `.btn.btn-toggle`. The DELETE button MUST use `.btn.btn-cv-delete` (red outline). Display labels MUST use `.cv-zone-label` and `.cv-upload-date`. The PREVIEW link MUST use `.cv-preview-link`.

(Previously: CV zone had dashed border, no `.btn-cv-upload` CSS class existed, labels used `.cv-label`/`.cv-date`)

#### Scenario: Upload valid PDF

- GIVEN the user has not uploaded any CV
- WHEN the user selects a valid PDF and clicks UPLOAD (`.btn.btn-toggle`)
- THEN the file is saved to `data/cv/` and a preview link appears with today's date

#### Scenario: Upload non-PDF

- GIVEN the upload form is visible
- WHEN the user selects a `.png` file
- THEN an error message says "Only PDF files are accepted" and no file is stored

#### Scenario: Delete existing CV

- GIVEN a CV is uploaded and its preview is visible
- WHEN the user clicks DELETE (`.btn.btn-cv-delete`) and confirms
- THEN the PDF file is removed from disk, the DB row is deleted, and the upload form resets to empty

### Requirement: CV Field Type

A field with type `file` SHALL render as a CV upload zone (drag-and-drop or file picker) instead of a text input. The system MUST NOT allow more than one `file`-type field. No visual changes — file-type field behavior is unaffected.

## ADDED Requirements

### Requirement: Platform Display

The system MUST display saved platforms (name + URL) in a list. The ADD PLATFORM form MUST insert new entries. The REMOVE button MUST delete the platform.

Each platform item MUST use `.platform-item-name`, `.platform-item-url` classes. The add form inputs MUST use `.datos-form-input` inside `.datos-form-group` + `.datos-form-label` wrappers. The ADD PLATFORM button MUST use `.btn.btn-toggle`. The REMOVE button MUST use `.btn.btn-platform-remove` (red outline).

#### Scenario: Display and add platform

- GIVEN saved platforms with name "LinkedIn" and URL "https://linkedin.com"
- WHEN the panel loads
- THEN the platform displays with `.platform-item-name` and `.platform-item-url`
- AND a new platform can be added via `.datos-form-input` fields and `.btn.btn-toggle`

#### Scenario: Remove platform

- GIVEN a saved platform "Indeed"
- WHEN the user clicks REMOVE (`.btn.btn-platform-remove`)
- THEN the platform is deleted from the database and its item disappears

### Requirement: CSS Integrity

The CSS for the data panel MUST NOT contain hardcoded color fallbacks (e.g., `var(--accent, #a855f7)`, `var(--accent2, #22d3ee)`) — all color references MUST use bare CSS custom properties. A syntax error at `.btn-platform-remove` (orphaned `text-transform`) MUST be fixed. The `.data-panel` border MUST use `var(--border-muted)` not `var(--accent)`. The `.btn-cv-upload` CSS class MUST be added with accent outline pattern (transparent bg, `var(--accent)` color/border).

#### Scenario: Syntax error fixed

- GIVEN the CSS has an orphaned `text-transform` after `.btn-platform-remove`
- WHEN the spec is applied
- THEN the orphaned property is moved into `.btn-platform-remove` and the CSS validates without parse errors

#### Scenario: Hardcoded fallbacks removed

- GIVEN `.btn-save` references `var(--accent2, #22d3ee)` and `.btn-add-field` references `var(--accent, #a855f7)`
- WHEN the spec is applied
- THEN those rules use `var(--accent2)` and `var(--accent)` only, without inline RGB fallbacks
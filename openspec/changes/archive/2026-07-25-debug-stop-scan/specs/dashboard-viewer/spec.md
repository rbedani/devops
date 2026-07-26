# Delta for dashboard-viewer

## ADDED Requirements

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
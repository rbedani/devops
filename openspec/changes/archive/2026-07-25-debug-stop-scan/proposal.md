# Proposal: Debug Stop Scan

## Intent

When debug mode is active and a scan is running, users have no way to cancel a running scan. This adds a STOP button in the progress bar that terminates the subprocess and resets state — avoiding waiting for a scan that may be unwanted or misconfigured.

## Scope

### In Scope
1. `asyncio.Event` cancellation signal in `ScanState`, checked by `run_scan()`
2. `GET /scan/stop` endpoint that sets the cancel signal and terminates the running subprocess
3. STOP button in `progress.html` partial — visible only when debug is active AND scan is running
4. JS wiring: STOP click → fetch `/scan/stop` → close SSE → re-enable SCAN button → collapse progress

### Out of Scope
- STOP button outside debug mode (non-debug scans must always complete)
- Pause/resume semantics
- Platform-level cancellation (stops the whole scan, not individual platforms)
- Keyboard shortcuts for stop

## Capabilities

### New Capabilities
None. Addition is a delta to existing `dashboard-viewer` spec.

### Modified Capabilities
- `dashboard-viewer`/Debug Mode: gains stop-button behavior in progress bar when debug is active

## Approach

- Add `cancel: asyncio.Event` to `ScanState`. `reset()` creates a fresh `Event` (not cleared).
- In `run_scan()`: before each platform subprocess, and after each stdout line, check `state.cancel.is_set()`. If set, kill the subprocess (`proc.terminate()` / `proc.kill()` with timeout), break the loop, set `running=False`.
- Add `GET /scan/stop`: sets `scan_state.cancel`, blocks briefly on event loop to let the subprocess die, returns empty progress partial.
- In `progress.html`: if `state.running and debug_mode`, render a STOP button as an HTMX-triggered element.
- In `script.js`: add a listener for htmx:afterRequest on `/scan/stop` that closes the SSE, re-enables SCAN, and collapses the progress container.
- The SSE `event_generator` in `/scan/status` already exits when `state.running` becomes False — once the cancel signal stops the subprocess, SSE naturally terminates.

For subprocess termination: send SIGTERM, wait 500ms, then SIGKILL if still alive. This avoids hanging on stuck scrapers.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/dashboard/scan.py` | Modified | Add cancel event to ScanState; check + kill subprocess in run_scan loop |
| `src/dashboard/server.py` | Modified | Add GET /scan/stop route; pass debug to template context in progress partial |
| `src/dashboard/templates/partials/progress.html` | Modified | Conditional STOP button when debug + running |
| `src/dashboard/static/script.js` | Modified | Stop button click handler → close SSE, re-enable SCAN |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Subprocess not responding to SIGTERM | Low | Fallback to SIGKILL after 500ms timeout |
| Race: stop called right as scan completes | Low | Cancel event + running flag gated; idempotent kill (already-exited subprocess raises no error) |

## Rollback Plan

Revert all 4 files. No DB schema changes. No migration. Pure additive code.

## Dependencies

None. Self-contained server-side + client-side changes.

## Success Criteria

- [ ] STOP button renders in progress partial only when debug checkbox ON and scan running
- [ ] Clicking STOP terminates the subprocess within 1s
- [ ] SSE closes, SCAN button re-enables, progress collapses
- [ ] Cancel during platform N moves to N+1 not executed (platform N killed, remaining skipped)
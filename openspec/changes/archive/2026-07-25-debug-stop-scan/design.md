# Design: Debug Stop Scan

## Technical Approach

Add an `asyncio.Event` cancellation signal to `ScanState`. The `run_scan()` loop checks it before each platform and after each stdout line. `GET /scan/stop` sets the event and kills the subprocess. The STOP button appears in `progress.html` via HTMX. JS closes the SSE stream on stop and resets UI.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|-------------|-----------|
| Cancel mechanism | `asyncio.Event` on `ScanState` | `proc.terminate()` from outside | `asyncio.Event` is cooperative, works with async loops, and gives the `run_scan()` function a clean exit point to flush state |
| Kill escalation | `terminate()` → 500ms → `kill()` | Just `kill()`, just `terminate()` | SIGTERM for graceful shutdown; SIGKILL as fallback for stuck scrapers. 500ms matches spec requirement |
| Stop route response | Empty progress partial | Redirect, JSON response | Returns the same progress partial HTMX expects, letting JS handle the UI reset via `htmx:afterRequest` listener |
| Template scope | `debug_mode` passed explicitly to progress partial | Reading `DEBUG_MODE` env directly | Keeps template logic consistent with existing pattern (see `/` route passing `debug_mode`) |

## Data Flow

```
User clicks STOP
       │
       ▼
  progress.html ──hx-get──▶  GET /scan/stop
       │                          │
       │                    set state.cancel
       │                    proc.terminate()
       │                    await 500ms max
       │                    if alive → proc.kill()
       │                    loop breaks
       │                    state.running = False
       │                          │
       │                    ◀── returns progress partial
       │
       ▼
  htmx:afterRequest
       │
       ├── eventSource.close()   (SSE stops naturally — event_generator sees running=False)
       ├── enable scan button
       └── collapse progress container
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/dashboard/scan.py` | Modify | Add `cancel: asyncio.Event` to `ScanState`. `reset()` creates fresh Event. In `run_scan()`: check cancel before each platform and after each stdout line. On cancel → kill subprocess, break loop, set `running=False` |
| `src/dashboard/server.py` | Modify | Add `GET /scan/stop` route. Pass `debug_mode` to progress template context. Set cancel event, block briefly on subprocess death, return progress partial |
| `src/dashboard/templates/partials/progress.html` | Modify | Conditional STOP button: `{% if state.running and debug_mode %}` with `hx-get="/scan/stop" hx-target="#progress-container" hx-swap="innerHTML"` |
| `src/dashboard/static/script.js` | Modify | Add `htmx:afterRequest` listener for `/scan/stop` path: close SSE, `enableScanButton()`, collapse `#progress-container`, kill dino renderer |

## Interfaces / Contracts

```python
# New field on ScanState
@dataclass
class ScanState:
    running: bool = False
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    # ... existing fields unchanged

    def reset(self) -> None:
        # ... existing reset
        self.cancel = asyncio.Event()  # fresh, not set
```

```python
# New route — server.py
@app.get("/scan/stop", response_class=HTMLResponse)
async def stop_scan(request: Request) -> HTMLResponse:
    scan_state.cancel.set()
    # Subprocess death handled inside run_scan() loop check
    # Return empty progress partial for HTMX swap
    return templates.TemplateResponse(
        request, "partials/progress.html",
        {"state": scan_state, "debug_mode": DEBUG_MODE},
    )
```

```python
# Cancel check inside run_scan() loop — scan.py
for i, platform in enumerate(selected):
    if state.cancel.is_set():
        break
    state.current_target = platform
    # ... subprocess creation ...
    async for line_raw in proc.stdout:
        if state.cancel.is_set():
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            break
        # ... existing line parsing ...
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `ScanState.cancel` event set/get | Mock event, verify `run_scan()` breaks loop and kills subprocess |
| Unit | Subprocess kill escalation | Mock `proc.terminate()`, simulate no-exit, verify `proc.kill()` called after 500ms |
| Unit | `reset()` creates fresh Event | Verify `reset()` followed by `is_set()` returns False |
| E2E | STOP button visibility | Start scan in debug mode, verify STOP renders; without debug, verify it does not |
| E2E | Stop mid-scan | Start scan, click STOP, verify SSE closes, SCAN re-enables, progress collapses |
| E2E | Idempotent stop | Click STOP after natural completion — no error |

## Threat Matrix

N/A — no routing changes, shell commands, VCS/PR automation, executable-file classification, or process-integration boundaries beyond the existing `asyncio.create_subprocess_exec` pattern (which is direct exec, not shell). Subprocess termination uses safe asyncio methods (`terminate()`, `kill()`, `wait()`), no shell or file-system path execution.

## Migration / Rollout

No migration required. Pure additive code paths.

## Open Questions

- [ ] What is the exact CSS class/ID for the progress container to collapse it from JS? Need to inspect the HTML structure — currently `progress-container` is referenced in `script.js`.
- [ ] Should the STOP button be an inline button inside `.scan-progress` or a separate element sibling to the progress bar? (Proposal says "in the progress bar" — inline inside `.scan-progress` div)
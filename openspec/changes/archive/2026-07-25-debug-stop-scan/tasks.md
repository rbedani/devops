# Tasks: Debug Stop Scan

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~140 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Cancel signal + stop route + UI | PR 1 | `pytest -v tests/unit/test_dashboard_backend.py -k "TestCancel\|TestScanStop\|TestStopButton"` | Start scan in debug, click STOP | Revert 4 files — pure additive |

## Phase 1: Foundation — ScanState cancel field

- [x] 1.1 (RED) Tests: `cancel` default is_set()=false; `reset()` creates fresh Event
- [x] 1.2 (GREEN) Add `cancel: asyncio.Event = field(default_factory=asyncio.Event)` to ScanState; `reset()` sets `self.cancel = asyncio.Event()`

## Phase 2: Core — Cancel check + subprocess kill in run_scan

- [x] 2.1 (RED) Tests: cancel before platform breaks loop; cancel mid-line terminates SIGTERM → 500ms → SIGKILL
- [x] 2.2 (GREEN) In `run_scan()`: check `state.cancel.is_set()` before each platform iteration; after each stdout line, if cancelled: `proc.terminate()`, `asyncio.wait_for(proc.wait(), 0.5)`, on TimeoutError `proc.kill()`, break loop

## Phase 3: Route + template wiring

- [x] 3.1 (RED) Tests: `GET /scan/stop` returns 200 HTML; sets `state.cancel.is_set()`; idempotent when scan already stopped
- [x] 3.2 (GREEN) Add `GET /scan/stop` route: set `scan_state.cancel.set()`, return progress partial with `{"state": scan_state, "debug_mode": DEBUG_MODE}`
- [x] 3.3 (GREEN) In `GET /scan`: pass `debug_mode` to progress template context (already matches `/` pattern)

## Phase 4: UI — STOP button + JS handler

- [x] 4.1 (RED) Tests: progress partial renders STOP button when `state.running and debug_mode`; hides when either false
- [x] 4.2 (GREEN) In `progress.html`: `{% if state.running and debug_mode %}<button class="btn btn-stop" hx-get="/scan/stop" hx-target="#progress-container" hx-swap="innerHTML">STOP</button>{% endif %}`
- [x] 4.3 (RED) Tests: script.js contains `htmx:afterRequest` handler for `/scan/stop` path; calls `eventSource.close()`, `enableScanButton()`, collapses progress, stops dino renderer
- [x] 4.4 (GREEN) In `script.js`: add `htmx:afterRequest` listener matching `/scan/stop` path → close SSE, `enableScanButton()`, `progressContainer.classList.remove('expanded')`, `dinoRenderer = null`

## Phase 5: Verify

- [x] 5.1 Run `pytest tests/unit/test_dashboard_backend.py -v --tb=short` — all tests pass
- [x] 5.2 Manual: start scan in debug mode, STOP button visible, click terminates subprocess, SSE closes, SCAN re-enables
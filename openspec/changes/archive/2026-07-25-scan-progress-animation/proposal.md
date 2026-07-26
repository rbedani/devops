# Proposal: Scan Progress Animation

## Intent

The Scan button triggers a job search via HTMX → SSE, and the full infrastructure for real-time progress tracking already exists (CSS progress bar, SSE endpoint, `ScanState.progress_pct`). However, `progress_pct` only updates when an entire platform's subprocess completes. With a single LinkedIn platform, the bar jumps 0% → 100% instantly, making the animation invisible.

## Scope

### In Scope
- **Emit per-target progress**: `run_search.py` writes `PROGRESS:<target_name>:<pct>` to stdout after each target completes
- **Parse progress in scan adapter**: `run_scan()` in `scan.py` parses `PROGRESS` lines from subprocess stdout and updates `state.progress_pct` per-target instead of per-platform
- **Granular target count**: pass total target count to `scan.py` so progress is divided by targets, not platforms

### Out of Scope
- Sub-target progress (individual job pages within a target) — `run_target()` remains opaque
- UI changes — the existing CSS/JS/SSE pipeline already handles rendering
- New platforms or target types

## Capabilities

### New Capabilities

None. This is an internal fix — no spec-level behavior changes.

### Modified Capabilities

None. Existing requirements are unchanged; the progress bar will simply render intermediate states it was already designed to handle.

## Approach

**Option A — Parse subprocess stdout** (from exploration):

1. **In `scripts/run_search.py`**: after each target in `main()` (line 96), emit `print(f"PROGRESS:{target.name}:{pct}%")` using `(completed / total) * 100`.
2. **In `src/dashboard/scan.py`**: while iterating over stdout lines in `run_scan()`, detect lines matching `^PROGRESS:([^:]+):([\d.]+)%` and update `state.progress_pct`, `state.current_target`, and `state.targets_completed` in near-real-time.

This requires no new infrastructure — `run_scan()` already reads stdout line-by-line via `proc.stdout`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `scripts/run_search.py` | Modified | Add `PROGRESS:` print after each completed target in `main()` |
| `src/dashboard/scan.py` | Modified | Parse `PROGRESS:` lines in the stdout loop of `run_scan()` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `PROGRESS:` prefix conflicts with `format_jobs_table()` output | Low | `format_jobs_table` prints to stdout AFTER the target loop; progress lines are per-target, not post-loop |

## Rollback Plan

Revert the two modified files to their commit-previous state. The SSE endpoint and frontend are unaffected — they will simply show the old 0→100 jump until reverted.

## Dependencies

None.

## Success Criteria

- [ ] Scan with 3+ targets shows progress bar stepping through each target (e.g., 33%, 66%, 100%)
- [ ] Single-target scan still reaches 100% on completion
- [ ] No regressions in collected job results or final summary output
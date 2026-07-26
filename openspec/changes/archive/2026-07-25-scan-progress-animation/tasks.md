# Tasks: Scan Progress Animation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~15–25 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

## Phase 1: Foundation — Emit Progress from run_search.py

- [x] 1.1 Compute `total = len(enabled)` before the `for target in enabled:` loop in `main()` (line 95)
- [x] 1.2 After `all_jobs.extend(jobs)` (line 97), calculate `pct = round((completed / total) * 100, 1)` and emit `print(f"PROGRESS:{target.name}:{pct}%")`

## Phase 2: Core — Parse Progress in scan.py

- [x] 2.1 Add compiled regex `re.compile(r"^PROGRESS:([^:]+):([\d.]+)%$")` in `run_scan()`
- [x] 2.2 In the stdout loop (line 98), for each line: if regex matches, parse target name and pct, update `state.progress_pct`, `state.current_target`, `state.targets_completed`; skip appending PROGRESS lines to `state.log_lines`
- [x] 2.3 Verify non-PROGRESS lines still append to `log_lines` and non-matching lines are unaffected

## Testing Note

No test suite exists for `scripts/run_search.py` or `src/dashboard/scan.py` subprocess parsing. The existing `test_dashboard_backend.py` mocks the subprocess and is unaffected by this additive change. Skipping test tasks per orchestrator guidance.
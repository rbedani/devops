# Tasks: Flat Design + Playwright Audit

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~200–225 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast (low risk) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | CSS refactor + audit script | Single PR | `grep -c 'border-radius\|box-shadow\|text-shadow' src/dashboard/static/style.css` (must be 0) | `python scripts/audit_flat.py` against live dashboard on localhost:3311 | `git checkout HEAD -- src/dashboard/static/style.css` |

## Phase 1: CSS Flat Refactor

- [x] 1.1 Delete CSS variables `--border-glow`, `--shadow-glow`, `--shadow-cyan` and their comment
- [x] 1.2 Remove `box-shadow` from `.dashboard-header`
- [x] 1.3 Remove `text-shadow` from `.dashboard-title`
- [x] 1.4 Set `border-radius: 0` on `.menu-row`; remove `box-shadow`
- [x] 1.5 Set `border-radius: 0` on `.search-box`; remove `box-shadow` (normal + focus state); drop `box-shadow` from `transition`
- [x] 1.6 Set `border-radius: 0` on `.btn` class
- [x] 1.7 Replace `linear-gradient` background on `.btn-scan` with solid `var(--accent-purple)`; remove `box-shadow`
- [x] 1.8 Remove `box-shadow` from `.btn-scan:hover`, `.btn-toggle`, `.btn-toggle:hover`, `.btn-page:hover`, `.btn-clean:hover`
- [x] 1.9 Set `border-radius: 0` on `.btn-page`, `.debug-checkbox`, `.job-link`, `.per-page-select`
- [x] 1.10 Set `border-radius: 0` on `.job-table`; remove `box-shadow`
- [x] 1.11 Set `border-radius: 0` on `.status-badge` (pill → flat rectangle); remove `box-shadow` from all status variants
- [x] 1.12 Set `border-radius: 0` on `.pagination-bar`; remove `box-shadow`
- [x] 1.13 Replace `linear-gradient` on `.progress-fill` with solid `var(--accent-purple)`; remove `box-shadow`
- [x] 1.14 Remove `box-shadow` from `.scan-progress-done .progress-fill` and `.scan-progress-error .progress-fill`
- [x] 1.15 Set `border-radius: 0` on scrollbar thumb
- [x] 1.16 Verify: `grep -c 'border-radius\|box-shadow\|text-shadow' src/dashboard/static/style.css` returns 0

## Phase 2: Playwright Audit Script

- [x] 2.1 Create `scripts/audit_flat.py` — `playwright.sync_api`, headless Chromium, debug mode flow:
  - Screenshot 1: initial dashboard (`01-initial.png`)
  - Screenshot 2: DEBUG checkbox ON with CLEAN DB visible (`02-debug-on.png`)
  - Screenshot 3: after CLEAN DB click — empty table state (`03-after-clean.png`)
  - Screenshot 4: debug toggle OFF — dashboard returns to normal (`04-debug-off.png`)
  - `DASHBOARD_URL` env var (default `http://localhost:3311`), graceful error handling, exit 0/1
- [x] 2.2 Create `reports/ui-audit/` directory; add `/reports/` to `.gitignore`
- [x] 2.3 Run `python scripts/audit_flat.py` against running dashboard; verify 4 PNGs in `reports/ui-audit/`

## Phase 3: Spec Docs

- [x] 3.1 Update `openspec/specs/dashboard-viewer/spec.md` — "Theme applied" scenario: replace glow/shadow assertions with flat-style assertions; keep cyberpunk palette assertions

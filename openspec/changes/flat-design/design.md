# Design: Flat Design + Playwright Audit

## Technical Approach

Two parallel workstreams: (1) **CSS flat refactor** — strip all `border-radius`, `box-shadow`, `text-shadow`, and glow effects from `style.css` while preserving the cyberpunk color palette; (2) **Playwright audit script** — standalone Python script that proves the debug mode flow works end-to-end with visual screenshots.

The refactor is purely declarative (CSS properties only), and the audit script is additive (no existing code modified). Both workstreams are independent.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|-------------|-----------|
| CSS surface | Replace in-place | CSS variables for radius/shadow | Only 573 lines, single pass. Variables would add indirection with no maintainability gain for a one-time change. |
| Shadow removal | Delete declarations | Set to `none`/`0` | Delete reduces noise and prevents accidental re-enable via variable swap. |
| Gradient removal | Replace with solid fill | Keep gradient but strip radius | Proposal explicitly calls for flat solid colors on `.btn-scan` and progress fill. |
| Audit script language | Python (sync_api) | JS/TS, pytest | Matches existing `scripts/` convention (Python, no test runner). `.venv` already has Playwright. |
| Audit output dir | `reports/ui-audit/` | `reports/flat-audit/` | From proposal. Aligned with project convention (no `reports/` exists yet, but `reports/` is standard). |
| Audit flow | Debug mode sequence | Full CRUD test | Debug mode exercises the most UI states (loading, clean, buttons, progress) in minimal steps. |

## Data Flow

**CSS**: No runtime data flow. Static CSS file served by FastAPI static mount. Changes are purely visual.

**Audit script**:

```
Script ──playwright──→ Chromium (headless) ──HTTP──→ localhost:3311
  │                        │
  │                        └── Screenshot → reports/ui-audit/*.png
  │
  └── exit code 0/1
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/dashboard/static/style.css` | Modify | Strip `border-radius`, `box-shadow`, `text-shadow`, glow variables, gradient backgrounds |
| `scripts/audit_flat.py` | Create | Playwright audit script: debug mode flow, 4 screenshots, exit code reporting |
| `reports/ui-audit/` | Create | Screenshot output directory (gitignored) |

## Interfaces / Contracts

### Audit Script Contract

```python
# scripts/audit_flat.py
# Usage: python scripts/audit_flat.py
# Requires: DASHBOARD_URL=http://localhost:3311 (default)
# Output: reports/ui-audit/01-initial.png ... 04-scan-ready.png
# Exit: 0 on success, 1 on failure
```

The script MUST:
- Accept `DASHBOARD_URL` env var (default `http://localhost:3311`)
- Use `playwright.sync_api` with headless Chromium
- Save screenshots under `reports/ui-audit/`
- Use `try/finally` for browser context cleanup
- Return exit code 0 if all steps complete, 1 on any error

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Visual | Flat CSS rendering | Manual visual check after apply; audit script screenshots verify no breakage |
| E2E | Debug mode flow | `scripts/audit_flat.py` — run against live dashboard, assert 4 screenshots created |
| Static | No shadow/radius leak | `grep -c 'border-radius\|box-shadow\|text-shadow' style.css` must return 0 |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The Playwright script uses the high-level `sync_api` which manages the browser subprocess internally; no raw shell commands or subprocess invocation in the design.

## Migration / Rollout

No migration required. Single-file CSS change is atomic. Audit script is additive. Rollback: `git checkout HEAD -- src/dashboard/static/style.css`.

## Open Questions

None.
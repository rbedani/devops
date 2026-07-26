# Exploration: DevOps Project — Comprehensive Codebase Overview

> **Date**: 2026-07-24
> **Project**: Framework Browser Jobs — Playwright-based job listing scraper
> **Mode**: Standalone exploration (no named change)

---

## Current State

### Architecture Overview

The project is a modular Python 3.11+ job listing scraper with four cleanly separated layers:

1. **Scrapers** (`src/scrapers/`) — Playwright-based browser automation. `BaseScraper` ABC provides lifecycle management (browser start/stop), tag auto-detection pipeline, and DB persistence. `LinkedInScraper` implements site-specific `login()`, `scrape_search()`, and `scrape_detail()`.

2. **Domain Model** (`src/models/job.py`) — `Job` and `JobTag` dataclasses with dynamic tag support (key/value/confidence). Convenience properties (`modality`, `salary`, etc.) map to tags.

3. **Tag Detection** (`src/tags/detector.py`) — `TagRegistry` with pluggable `TagDetector` extractors. Six built-in detectors: modality (remote/hybrid/onsite), schedule, salary (EUR/USD with false-positive prevention), vacancies, applicants, publication date.

4. **DB + Alerts** (`src/db/database.py`, `src/alerts/telegram.py`) — SQLite with WAL mode, upsert by URL, `search_by_tag` via LIKE. Telegram formatters for single, table, and markdown-table output.

### Configuration

- `src/config/search.py` — `SearchTarget`+`SearchFilters` dataclasses with LinkedIn param mapping, serialization, `matches_job()` post-filter
- `src/config/settings.py` — `AppConfig`, ansible-vault secret loader, JSON config loader
- `config/targets.json` — Two pre-configured targets: "devops_remote_españa" and "devops_remote_spain"

### Test Coverage

- **22 unit tests** across 6 test files, all passing
- **Coverage gaps**: No integration tests, no e2e tests, no tests for `BaseScraper` lifecycle or `save_many`, no tests for Telegram's `_format_salary()`, no tests for `Settings` config loading
- **Test quality**: Good isolation (fixtures for DB), good boundary testing on detectors, solid salary edge cases

---

## What Works Well

### Strengths

1. **Clean Separation of Concerns**: The ABC pattern with `BaseScraper` enables adding new platforms by implementing just 3 methods. The tag registry is truly pluggable (`TagRegistry.register()` is trivial to extend).

2. **Solid Salary Detection**: The `_detect_salary()` function handles EUR/USD formats, European dot/decimal notation, "k" suffix, "bruto anual" context, and false-positive prevention (year detection, non-salary range filtering). This is the most sophisticated module in the codebase.

3. **Good Data Model**: `JobTag` with confidence scores enables probabilistic tag merging. The `matches_job()` post-filter on modality prevents mismatches from search-time LinkedIn filtering.

4. **Test Quality**: The unit tests use fixtures, avoid mocking Playwright (sensible — these are logic tests), and cover edge cases well (e.g., salary with comma/dot thousands, no false positives).

5. **Configuration Separation**: Search targets are pure JSON, no code changes needed to add new searches. Serializable dataclasses with round-trip tested.

6. **Context Manager Lifecycle**: `BaseScraper.__aenter__`/`__aexit__` and `JobDatabase.__enter__`/`__exit__` make resource cleanup reliable.

---

## What Needs Improvement

### Critical Issues

#### 1. LinkedIn Selector Fragility
The CSS selectors in `linkedin.py` use fallback patterns like `".base-card, .job-search-card"` and `"a.base-card__full-link, a.job-search-card__title-link"`. LinkedIn frequently changes class names — these will break silently. **No monitoring or health checks** exist for scraper success rates.

#### 2. No Retry Logic
If `scrape_search()` times out (25s), it returns `[]`. If `scrape_detail()` times out, it returns an empty Job. No exponential backoff, no retry on transient failures. A single network hiccup loses an entire search target's results.

#### 3. SQL Injection Risk in `search_by_tag()`
```python
def search_by_tag(self, key: str, value: str) -> list[Job]:
    conn.execute(
        "SELECT * FROM jobs WHERE tags LIKE ? ORDER BY scraped_at DESC",
        (f'%{key}%{value}%',),
    )
```
While parameterized, the concatenation of `key` and `value` into a single LIKE pattern means `key="%"` + `value="%"` would match all rows. Not exploitable for injection (parameterized), but a logic leak — any user with DB access could craft queries that match unintended rows.

#### 4. No Rate Limiting or Polite Scraping
LinkedIn actively blocks headless browsers. The scraper has no:
- Random delays between requests
- Cookie/session persistence between runs
- Proxy rotation
- Human-like behavior (mouse movements, scrolling patterns)

The `wait_for_timeout(3000)` is a static delay — no adaptive waiting based on page state.

### Moderate Issues

#### 5. Telegram `_format_salary()` is Undefined Behavior
```python
def _format_salary(raw: str) -> str:
    if any(sym in raw for sym in ["€", "$", "USD", "EUR", "£"]):
        return raw  # passes through as-is
    if raw and any(c.isdigit() for c in raw):
        return f"€{raw} {SALARY_DEFAULT_PERIOD}"  # assumes EUR
    return raw
```
If a detected salary is `"USD 80k-100k"`, it passes through untouched — the function only prepends EUR to bare numbers. But what about `"45.000€ - 55.000€ bruto anual"` (a detected pattern)? It has a digit but also has `€`, so it passes through with no normalization. The "EUR default" assumption is undocumented and would be wrong for US-focused targets.

#### 6. `save_many()` is not Batch
```python
def save_many(self, jobs: list[Job]) -> list[int]:
    return [self.save_job(j) for j in jobs]
```
Each job commits individually — O(N) transactions instead of a single batch with `executemany`. For 25 jobs per target × N targets, this is 50+ separate commits.

#### 7. No Deduplication Across Sources
The DB uses `url` as the UNIQUE key. If the same job appears on LinkedIn and Indeed, it gets stored twice with different URLs. There's no cross-source dedup (e.g., by company+title+location hash).

#### 8. `_detect_modality` Ignores Description in Some Cases
The detector concatenates `f"{title} {description}"` but modality keywords in actual job descriptions (e.g., "This role is fully remote") work fine. However, it only detects **one modality** per job — the first matched. If a job says "Remoto con opción híbrida", only "Remoto" is captured.

#### 9. Config Path Reliance on CWD
`scripts/run_search.py` uses `Path("config/targets.json")` and `Path("jobs.db")` — relative to the working directory. Running from `scripts/` would break. All scripts share this pattern.

### Minor Issues

#### 10. `scraped_at` Uses `datetime.utcnow()` (Deprecated)
Python 3.12+ replaces `utcnow()` with `datetime.now(datetime.UTC)`. The project requires 3.11+, so imminent breakage.

#### 11. `requests` in Dependencies but Unused
`pyproject.toml` lists `requests>=2.31` as a production dependency. No module imports `requests`. Could be for future Telegram HTTP calls, but currently dead weight.

#### 12. No CI/CD Configuration
No GitHub Actions, no pre-commit config, no Dockerfile. Tests can only be run manually.

#### 13. No Type Annotations on `_parse_card`'s `card` Parameter
```python
async def _parse_card(self, card: any) -> Job | None:
```
Uses `any` instead of `playwright.async_api.ElementHandle`. This disables type checking on the most error-prone function.

#### 14. ansible-vault Dependency in Config
`load_vault_secret()` shells out to `ansible-vault` and requires `vault_password.txt` on disk. This is a fragile dependency — no fallback, no env var alternative, no error recovery if ansible-vault is missing.

---

## Affected Areas

| File | Issue(s) |
|------|----------|
| `src/scrapers/linkedin.py` | Selector fragility, no retry, no rate limiting, `any` type |
| `src/scrapers/base.py` | `save_many` not batched, no connection pooling |
| `src/db/database.py` | `search_by_tag` LIKE logic leak, no cross-source dedup |
| `src/tags/detector.py` | Single-modality limitation, no industry/benefits detectors |
| `src/alerts/telegram.py` | `_format_salary` undefined behavior, assumes EUR |
| `src/config/settings.py` | Relative paths, fragile ansible-vault shell-out |
| `scripts/*.py` | CWD-dependent paths, no argument parsing |
| `pyproject.toml` | `requests` unused, `utcnow()` deprecated |
| `.github/` | Missing entirely — no CI/CD |

---

## Improvement Opportunities

### Easy Wins (Low Effort, High Impact)

| # | Improvement | Effort | Impact |
|---|-------------|--------|--------|
| 1 | Add `--db-path` and `--config` CLI args to scripts via `argparse` | 1h | Eliminates CWD fragility |
| 2 | Replace `datetime.utcnow()` → `datetime.now(datetime.UTC)` | 5min | Future-proofing |
| 3 | Remove `requests` from deps (or keep but add telemetry use) | 5min | Clean dependency tree |
| 4 | Add `type: ignore` or proper `ElementHandle` type to `_parse_card` | 10min | Better type checking |
| 5 | Add CI (`.github/workflows/test.yml`) — just `pytest + ruff + mypy` | 30min | Baseline CI |

### Medium Wins (Medium Effort, High Impact)

| # | Improvement | Effort | Impact |
|---|-------------|--------|--------|
| 6 | **Retry + Circuit Breaker** for scrapers (3 retries with backoff, max failures before skip) | 2-3h | Resilience |
| 7 | **Rate Limiting + Polite Scraping** — random delays (2-6s), cookie persistence, browser fingerprinting | 3-4h | LinkedIn detection avoidance |
| 8 | **Selector Health Monitoring** — track parse success rate per selector, alert if < 50% | 2h | Early failure detection |
| 9 | **Batch DB writes** — `executemany` in `upsert_many` | 1h | Performance (50x fewer transactions) |
| 10 | **Integration tests** — mock Playwright page, test full scrape flow | 3-4h | Coverage for scraper logic |
| 11 | **Multi-platform support** — Add `IndeedScraper` or `ComputrabajoScraper` (easy with ABC pattern) | 4-6h per platform | More job sources |
| 12 | **Docker setup** — `Dockerfile` + `docker-compose.yml` with headless Chromium | 2h | Reproducible deployment |

### High Effort / Strategic

| # | Improvement | Effort | Impact |
|---|-------------|--------|--------|
| 13 | **Cross-source dedup** — hash company+title+location, store as fingerprint | 4-6h | Data quality |
| 14 | **Notification scheduling** — cron integration, daily/weekly digests, "new since last check" | 4-6h | Usability |
| 15 | **Web dashboard** — FastAPI/Flask frontend for browsing jobs with tag filters | 2-3 weeks | Major feature |
| 16 | **AI enrichment** — GPT/LLM integration for smarter tag detection (skills, seniority, industry) | 1-2 weeks | Smarter data |
| 17 | **Proxy rotation** — rotating residential proxies for LinkedIn scraping | 1-2 weeks | Scale |

---

## Approaches for Key Improvements

### Approach A: Scraper Resilience

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A1. Simple retry decorator** | Minimal code, easy to understand | No circuit breaker, no per-target failure tracking | Low |
| **A2. Circuit breaker on `BaseScraper`** | Stops hammering dead targets, logs failures | More complex, needs state management | Medium |
| **A3. External queue (Redis/SQS)** | Production-grade, decouples scrape from process | Overkill for current scale, infra complexity | High |

**Recommendation**: A2 — add retry + circuit breaker to `BaseScraper` with per-target failure tracking in a dict.

### Approach B: Multi-Platform Architecture

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **B1. One scraper per file** (current pattern) | Clean, testable, easy to add | Code duplication for common patterns | Low |
| **B2. Shared "job card parser" mixin** | DRY across platforms | Tight coupling, harder to test independently | Medium |
| **B3. Config-driven selectors** (YAML/JSON per platform) | Zero-code platform additions | Complex mapping, can't handle site-specific JS logic | High |

**Recommendation**: B1 for now — the current ABC pattern is solid. Only refactor when adding the 3rd+ platform.

### Approach C: CI/CD Pipeline

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **C1. GitHub Actions (pytest only)** | 30 min setup, immediate value | No deployment automation | Low |
| **C2. GitHub Actions + Docker build** | Full CI/CD, deployable artifact | More YAML, registry setup | Medium |
| **C3. Pre-commit hooks** | Catches issues before commit | Local-only, no shared enforcement | Low |

**Recommendation**: C1 now, add C2 when there's a deployment target.

---

## Detected Gaps (Feature Wishlist)

1. **No scheduled execution** — only manual `python3 scripts/run_search.py`. No `cron` entry, no scheduler.
2. **No alert deduplication** — if the same job is scraped twice, Telegram sends duplicates. No "already notified" tracking.
3. **No search target groups** — targets are flat list. No "run these 3 daily, these 2 weekly" scheduling.
4. **No export** — no CSV/JSON export from DB for analysis.
5. **No "seen before" tracking** — no way to know if a job is new since last scrape (beyond `scraped_at` timestamp).
6. **No skill/technology detection** — tags are metadata-focused (modality, salary). No "Python", "AWS", "Kubernetes" detection from descriptions.
7. **No company blacklist/whitelist** — can't filter out recruiting agencies or specific companies.

---

## Risks

- **Scraper detection risk** (high): LinkedIn aggressively blocks headless browsers. Current implementation has zero evasion techniques.
- **Single point of failure** (medium): All scripts assume CWD is project root. Running from any other directory breaks.
- **Data quality risk** (medium): Salary detection regex is sophisticated but regex-only. No human validation or confidence thresholds for auto-send.
- **Secret management fragility** (low): `ansible-vault` shell-out has no graceful degradation if the vault password file is missing.
- **Python version risk** (low): `utcnow()` deprecation in 3.12 will trigger warnings, turning into errors in 3.14.

---

## Ready for Actionable Improvements

Yes — the following are ready for dedicated SDD changes:

1. **Scraper Resilience** — add retry, circuit breaker, and rate limiting to `BaseScraper`
2. **CI Pipeline** — add GitHub Actions for automated testing
3. **Multi-Platform Support** — add Indeed or Computrabajo scraper (prove the ABC pattern works)
4. **Scheduled Execution + Notification Dedup** — cron integration with "new since last check" tracking
5. **Integration Tests** — mock Playwright for full flow testing
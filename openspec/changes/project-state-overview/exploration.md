# Exploration: DevOps Project — Estado Global (Updated 2026-07-25)

> **Project**: Framework Browser Jobs — Playwright-based job listing scraper
> **Change Name**: project-state-overview
> **Mode**: Standalone exploration (hybrid artifact store)

---

## Executive Summary

Proyecto funcional de scraping de ofertas laborales con Playwright + FastAPI dashboard + Telegram alerts. Comenzó como scraper CLI (24 Jul), y en ~36h se agregó un dashboard completo con HTMX, progreso SSE, theme switch, responsive design para iPhone, y un sistema SDD completo con 4 cambios archivados y 1 en progreso.

---

## 1. Stack Tecnológico

| Capa | Tecnología | Versión/Detalle |
|------|-----------|-----------------|
| **Language** | Python | >=3.11 |
| **Browser Automation** | Playwright | >=1.40, Chromium headless |
| **Backend (Dashboard)** | FastAPI | >=0.109, con lifespan migration |
| **Server** | Uvicorn | >=0.27 |
| **Templates** | Jinja2 | >=3.1, con HTMX 1.9.12 (CDN) |
| **Database** | SQLite | WAL mode, row_factory |
| **Frontend** | Vanilla CSS + JS | Retro pixel aesthetic (Press Start 2P) |
| **Alerts** | Telegram | vía Hermes Agent (Markdown) |
| **Secrets** | ansible-vault | Shelling out to CLI |
| **Testing** | pytest + bats | pytest-cov, ruff, mypy |
| **Total lines** | ~3,043 across all source files | |

---

## 2. Componentes y Arquitectura

```
                    ┌──────────────────────────────┐
                    │     FastAPI Dashboard         │
                    │  (src/dashboard/server.py)     │
                    │  Routes: / /table /scan /data  │
                    │  SSE: /scan/status             │
                    └──────────┬───────────────────┘
                               │ subprocess
                    ┌──────────▼───────────────────┐
                    │   scripts/run_search.py       │
                    │   (PROGRESS: stdout protocol) │
                    └──────────┬───────────────────┘
                               │ async
          ┌────────────────────┼────────────────────┐
          │                    │                    │
┌─────────▼────────┐  ┌───────▼──────┐  ┌─────────▼────────┐
│ LinkedInScraper  │  │ TagRegistry  │  │  JobDatabase      │
│ login()          │  │ modalidad    │  │  SQLite (jobs.db) │
│ scrape_search()  │  │ salario      │  │  upsert by URL    │
│ scrape_detail()  │  │ horario      │  │  search, count    │
└──────────────────┘  │ postulados   │  └─────────┬────────┘
                      │ fecha_pub    │            │
                      └───────┬──────┘            │
                              │                    │
                    ┌─────────▼────────────────────▼──┐
                    │   alerts/telegram.py             │
                    │   format_job_alert()             │
                    │   format_jobs_table()            │
                    └────────────────────────────────┘
```

### 2.1 Core Framework (completado Jul 24)

- **`src/scrapers/base.py`** (126 lines) — ABC con `async with` lifecycle, browser launch (Chromium headless), auto-detection pipeline, DB persistence
- **`src/scrapers/linkedin.py`** (158 lines) — LinkedIn implementation con selectores CSS con fallback, parseo de cards y detail pages
- **`src/models/job.py`** (105 lines) — Dataclasses `Job` + `JobTag` con tags dinámicos (key/value/confidence), serialización JSON, acceso por propiedad
- **`src/tags/detector.py`** (289 lines) — `TagRegistry` con 6 detectores: modalidad (remote/hybrid/onsite), horario (full/part/contract), salario (EUR/USD con validación de falsos positivos), vacantes, postulados, fecha de publicación
- **`src/db/database.py`** (140 lines) — SQLite con WAL, upsert por URL, `get_all`, `count`, `search_by_tag` (LIKE), `delete_job`
- **`src/alerts/telegram.py`** (132 lines) — Formateadores Markdown para Telegram con emojis por tag, detección/simbología EUR
- **`src/config/search.py`** (145 lines) — `SearchTarget` + `SearchFilters` dataclasses, serialización JSON, mapeo a parámetros LinkedIn
- **`src/config/settings.py`** (83 lines) — `AppConfig`, cargador ansible-vault, carga desde JSON

### 2.2 Dashboard (agregado Jul 24-25)

- **`src/dashboard/server.py`** (339 lines) — FastAPI con:
  - `GET /` — Shell del dashboard con total_jobs y scan_running context
  - `GET /table` — Partial HTMX para tabla de trabajos (paginación, búsqueda cross-column)
  - `GET /scan` — Dispara scan asíncrono, retorna progress partial
  - `GET /scan/status` — SSE endpoint que emite eventos JSON con pct/target/log/done
  - `POST /clean-db` — Elimina todos los registros
  - `GET /select/toggle` — Toggle columna de checkboxes
  - `GET /data` — Formulario de datos personales (placeholder)
  - Migración aditiva: `ALTER TABLE jobs ADD COLUMN status` en startup
- **`src/dashboard/scan.py`** (120 lines) — `ScanState` singleton, subprocess adapter que lanza `run_search.py`, parsea stdout PROGRESS
- **`src/dashboard/templates/`** — 4 templates: `base.html` (shell con logo SVG, theme switch, DATA button), `index.html` (search, scan, select, auto-apply, debug), partials (`table.html`, `pagination.html`, `progress.html`, `data_form.html`)
- **`src/dashboard/static/`** — `style.css` (1004 lines, dual theme CSS custom properties, responsive 480/768/1024 breakpoints), `script.js` (217 lines, SSE listener, theme toggle, data button, select-all, auto-apply stub)

### 2.3 Service Management (agregado Jul 25)

- **`scripts/dashboard.sh`** (203 lines) — CLI bash: start/stop/restart/status/dev, PID file management, port checking, hot-reload dev mode
- **`scripts/run_dashboard.py`** (26 lines) — Entry point uvicorn con `DASHBOARD_PORT` env var
- **`tests/integration/test_dashboard_service.sh`** (272 lines) — Bats-compatible integración tests

### 2.4 Scraping Pipeline

- **`scripts/run_search.py`** (146 lines) — Orquestador: carga targets, filtra por `SCRAPE_PLATFORM`, ejecuta por target, emite `PROGRESS:` lines, filtra post-scrape por `SCAN_KEYWORD`
- **`config/targets.json`** — 2 targets: "devops_remote_españa" y "devops_remote_spain" (ambos LinkedIn, keywords devops+ansible)

---

## 3. Tests

### 3.1 Unit Tests (7 files, ~65+ tests total)

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_database.py` | 10 | CRUD completo, upsert, delete, context manager |
| `test_detector.py` | 12 | Modalidad, horario, salary, vacantes, registry |
| `test_job.py` | 7 | Job y JobTag creation, tags, serialization |
| `test_salary_eur.py` | 8 | Patrones EUR (rango, k-suffix, dot thousands, false positives) |
| `test_search.py` | 11 | SearchFilters, SearchTarget, serialize round-trip |
| `test_telegram.py` | 9 | format_job_alert, format_jobs_table, markdown table |
| `test_dashboard_backend.py` | ~50+ | ScanState, run_scan mocked, migration, server routes, frontend templates, CSS, JS, dark mode, platform combo, pagination, cross-column search |

### 3.2 Integration Tests

- **`test_dashboard_service.sh`** — 10 tests bash/bats para dashboard.sh (start/stop/status/restart/dev)

### 3.3 Test Gaps

- Sin tests para `BaseScraper` lifecycle (mock Playwright)
- Sin tests e2e (Playwright real scraping)
- Sin tests para `settings.py` (config loader + ansible-vault)
- Dashboard tests usan `TestClient` con mock de `run_scan` — no prueban el subprocess real

### 3.4 Configuración de Calidad

- **Ruff**: `E,F,I,N,UP,B,SIM` rules, line-length=100
- **Mypy**: `src/` con `warn_return_any=true`
- **pytest-cov**: disponible
- **CI**: No configurado (sin GitHub Actions)

---

## 4. Estado Git

### Branches
- **Solo `main`** — single branch, commits directos
- No hay PRs, no hay branches de feature

### Timeline de Commits (6 commits, todas Jul 24)

```
6cfc954 08:47  feat: initial project scaffold
f6242b9 08:58  feat: core framework — models, DB, tag detection, scrapers, alerts
7746806 09:35  fix: salary regex false positives + scraper timeout handling
0e43523 09:50  feat: modular search config + España/Spain targets
7af5c1c 10:06  feat: EUR salary detection + bruto anual + Telegram formatting
8daab97 10:23  fix: salary validation — parse first number only, reject years/noise
```

### Uncommitted Changes

Archivos **modificados** (tracked):
- `.engram/config.json` — Engram session config
- `.gitignore` — Added `.engram` y `/reports/`
- `pyproject.toml` — Added fastapi, uvicorn, jinja2, python-multipart deps
- `scripts/run_search.py` — PROGRESS protocol, SCRAPE_PLATFORM, SCAN_KEYWORD, DEBUG_MODE

Archivos **nuevos** (untracked):
- `openspec/` — Sistema SDD completo (config, cambios, specs)
- `src/dashboard/` — Todo el dashboard (server, scan, templates, static)
- `scripts/dashboard.sh`, `scripts/run_dashboard.py` — Service management
- `scripts/audit_dashboard_v*.py` — Archivos de auditoría UI
- `tests/unit/test_dashboard_backend.py` — Tests del dashboard
- `tests/integration/test_dashboard_service.sh` — Tests de servicio

---

## 5. Cambios Archivados (SDD History)

### 2026-07-24: Dashboard (completado)
- Proyecto FastAPI + HTMX completo
- 6 tareas implementadas (server, templates, CSS, JS, tests)
- Verificado y archivado

### 2026-07-25: Scan Progress Animation (completado)
- Animación de progreso SSE + PROGRESS protocol en subprocess
- `scan.py`, `progress.html`, SSE en `script.js`
- Verificado y archivado

### En Progreso: Dashboard Service (tasks completadas, sin verify/archive)
- `scripts/dashboard.sh` creado y testeado
- 7 tareas completadas (según tasks.md)
- Pendiente: verify y archive

---

## 6. Issues Conocidos y Deuda Técnica

### Críticos

1. **Selectores LinkedIn frágiles** — Usan CSS classes que LinkedIn cambia frecuentemente. Sin monitoreo de health.
2. **Sin retry/backoff** — Timeout en scrape_search o scrape_detail retorna vacío, sin reintento.
3. **Sin rate limiting** — Sin delays aleatorios, sin rotación de proxies, sin evasión de detección headless.
4. **`search_by_tag` LIKE leak** — Tags concatenados en LIKE pattern, permite match accidental con `%`.

### Moderados

5. **`save_many()` no es batch** — Cada job hace commit individual (O(N) transacciones).
6. **Sin dedup cross-source** — Misma oferta en LinkedIn e Indeed se guarda duplicada.
7. **`_format_salary()` comportamiento ambiguo** — Pasa EUR como default sin verificar moneda real.
8. **CWD-dependent paths** — Scripts usan `Path("config/targets.json")` relativo al CWD.
9. **`datetime.utcnow()` deprecated** — Python 3.12+ requiere `datetime.now(datetime.UTC)`.
10. **`requests` en deps pero no usado** — Dead weight.

### Específicos del Dashboard

11. **Sin autenticación** — Dashboard público en `0.0.0.0:3311`, sin login ni firewall.
12. **AUTO-APPLY es stub** — El botón existe, la lógica es `console.log()`.
13. **DATA form es placeholder** — Formulario con nombre/apellido, sin envío real.
14. **Sin test coverage para `style.css` responsive** — Los media queries no tienen tests.
15. **Sin test para scrollbar estilizado** — CSS scrollbar personalizado sin verificación.
16. **Sin type hints en `_parse_card`** — Usa `any` en vez de `ElementHandle`.
17. **CLEAN DB sin confirmación** — Borrado inmediato sin diálogo de confirmación.

---

## 7. Configuración y Despliegue

### Variables de Entorno

| Variable | Default | Uso |
|----------|---------|-----|
| `DASHBOARD_PORT` | `3311` | Puerto del dashboard |
| `DEBUG_MODE` | — | Debug checkbox → 3 results/scraper |
| `SCRAPE_PLATFORM` | — | Filtra targets por plataforma |
| `SCAN_KEYWORD` | — | Post-scrape filter por title/company |
| `PYTHONUNBUFFERED` | `1` | Set por scan.py para stdout streaming |
| `ANSIBLE_VAULT_PASSWORD` | — | (o vault_password.txt) para secrets |

### Cómo se ejecuta

```bash
# Dashboard dev mode (hot-reload)
./scripts/dashboard.sh dev

# Dashboard background service
DASHBOARD_PORT=3311 ./scripts/dashboard.sh start

# Scraper standalone
python -m scripts.run_search

# Scraper para una plataforma específica
SCRAPE_PLATFORM=linkedin python -m scripts.run_search

# Tests
pytest                          # Unit tests
bats tests/integration/         # Integration tests
ruff check .                    # Linter
mypy src/                       # Type checker
```

### Estado actual de jobs.db

Archivo SQLite presente en el project root (~jobs.db + WAL/SHM files). Contiene datos de scrapes previos.

---

## 8. Próximos Pasos Recomendados

### Inmediatos (1-2 sesiones)

1. **Commit del dashboard** — Hay ~12 archivos untracked + 4 modificados que representan el dashboard completo. Necesita commit o PR.
2. **Verify + Archive Dashboard Service** — Las tasks están completas, falta verificar y archivar el cambio.
3. **CI Pipeline** — GitHub Actions con pytest + ruff + mypy.

### Corto Plazo (3-5 sesiones)

4. **Scraper Resilience** — Retry con backoff, rate limiting, monitoreo de selectors.
5. **Multi-Platform** — Indeed o Computrabajo scraper.
6. **Dashboard auth** — Al menos un basic auth o token.
7. **Batch DB writes** — `executemany` en `upsert_many`.

### Mediano Plazo

8. **Scheduled scraping** — Cron o scheduler interno.
9. **Cross-source dedup** — Fingerprint por company+title+location.
10. **Docker deployment** — Dockerfile + docker-compose.
11. **AI enrichment** — Detección de skills/seniority con LLM.

---

## 9. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| LinkedIn bloquea headless | Alta | Alto | Rate limiting + proxies + fingerprint evasion |
| Selectores LinkedIn cambian | Media | Alto | Monitoreo de parse success rate |
| DB corrupción (SQLite single-writer) | Baja | Medio | WAL mode mitigates, pero no es multi-process safe |
| Sin CI — código quebrado no se detecta | Media | Medio | Agregar GitHub Actions es prioritario |
| ansible-vault passphrase perdido | Baja | Alto | Tener fallback .env para desarrollo local |

---

## Aprendizajes Clave

- El dashboard se construyó enteramente como código untracked (sin commits intermedios). Esto es riesgoso — si se pierde el working directory, se pierde ~2,000 líneas de código.
- SDD workflow híbrido funciona: openspec como source of truth + engram para persistencia cross-session.
- El sistema de progreso SSE + subprocess PROGRESS protocol es ingenioso pero frágil: el parseo de stdout asume formato exacto.
- La estructura SDD tiene 4 cambios archivados, 1 en progreso, y ningún cambio integrado aún via git. El repo está en estado pre-commit para todo el trabajo del dashboard.
# Job Dashboard — Framework Browser Jobs

> **Conseguir trabajo no es un juego, pero el proceso puede ser automatizado.**

Una herramienta agentica que concentra en una base de datos local todos los anuncios de empleo del mercado, los filtra inteligentemente, y prepara el terreno para la postulación automatizada.

## Propósito

El objetivo del proyecto es simple: **que Rodrigo consiga trabajo**.

La parte más difícil de la búsqueda laboral es estar 24/7 revisando todas las fuentes: LinkedIn, InfoJobs, Indeed, Computrabajo, Tecnoempleo… todas ofrecen un catálogo de vacantes, pero ninguna es **agentica**. Ninguna cruza datos, perfiles, ni rellena los largos y repetitivos formularios de inscripción por vos.

Ahí nace **Job Dashboard**: un framework que:

1. **Concentra** todos los anuncios en una base de datos SQLite con filtros inteligentes
2. **Estructura** tus datos personales — los campos necesarios para completar formularios, tu CV, y proveedores
3. **Automatiza** el proceso de búsqueda, filtrado, y eventualmente postulación

## Principios de diseño

### Independencia del dashboard
El dashboard debe funcionar **con o sin Hermes Agent**. Si mañana Hermes no funciona, el usuario sigue pudiendo consultar ofertas, ver estados, filtrar, y postularse manualmente. La interfaz web **no tiene capacidad agentica** — es puramente visual. Depende de SCAN para tener ofertas que mostrar.

### SCAN es el punto crítico
Si SCAN no funciona, el proyecto pierde todo sentido. Por eso tiene dos estrategias:

### Híbrido Script + Agente
- **Script directo**: Playwright ejecuta scripts para sitios con patrones estables. Rápido, eficiente, desatendido.
- **Agente adaptativo**: Cuando un sitio cambia y el script falla, Hermes Agent entra con prompts + skills para diagnosticar, extraer, y actualizar el script.

### Autonomía agentica de Hermes
Hermes Agent puede intervenir los módulos según sea necesario:
- Ante **patrones dinámicos** → usa skills para navegar el cambio
- Si es posible **automatizar sin skills** (ahorrar tokens) → plasma los cambios directamente en scripts
- **Variables personales** van a DATA
- **Variables de búsqueda/proceso** van a SCAN
- **Fallos en registro** van a STATUS

## Arquitectura

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                │
│                     ┌──────────────────────┐                   │
│                     │   JOB DASHBOARD      │                   │
│                     │  (FastAPI + HTMX)    │                   │
│                     │  Shell visual        │                   │
│                     │  Independiente de    │                   │
│                     │  Hermes              │                   │
│                     └──────────┬───────────┘                   │
│                                │                               │
│        ┌───────────────────────┼───────────────────────┐       │
│        │                       │                       │       │
│        ▼                       ▼                       ▼       │
│ ┌──────────────┐    ┌──────────────────┐    ┌────────────────┐ │
│ │  MÓDULO      │    │  MÓDULO          │    │  MÓDULO        │ │
│ │  SCAN        │    │  DATA            │    │  STATUS/TABLE  │ │
│ │              │    │                  │    │                │ │
│ │ Dual        │    │ Memoria personal │    │ Visor de       │ │
│ │ estrategia:  │    │                  │    │ ofertas con    │ │
│ │              │    │ Campos dinámicos │    │ estado:        │ │
│ │ Script ────► │    │ CV (PDF)         │    │                │ │
│ │ Rápido,      │    │ Proveedores      │    │ ✅ Postulado   │ │
│ │ patrones     │    │                  │    │    (auto)      │ │
│ │ estables     │    │ Auto-descubrim.  │    │ 👤 Postulado   │ │
│ │              │    │ de nuevos campos │    │    (manual)    │ │
│ │ Agente ────► │    │                  │    │ ⏳ Pendiente   │ │
│ │ Hermes       │    │                  │    │ ❌ Error       │ │
│ │ detecta      │    │                  │    │ ⚙️ Ajuste     │ │
│ │ cambios y    │    │                  │    │                │ │
│ │ actualiza    │    │                  │    │ Filtros +      │ │
│ │ el script    │    │                  │    │ búsqueda       │ │
│ └──────────────┘    └──────────────────┘    └────────────────┘ │
│                                │                               │
│                                ▼                               │
│                     ┌──────────────────────┐                   │
│                     │  MÓDULO API         │                   │
│                     │                      │                   │
│                     │ Interfaz REST para   │                   │
│                     │ Hermes:              │                   │
│                     │                      │                   │
│                     │ • Query jobs/status  │                   │
│                     │ • Get user data/CV   │                   │
│                     │ • Trigger SCAN       │                   │
│                     │ • Register auto-     │                   │
│                     │   apply results      │                   │
│                     │ • Add missing fields │                   │
│                     │   to DATA            │                   │
│                     └──────────┬───────────┘                   │
│                                │                               │
│                                ▼                               │
│                     ┌──────────────────────┐                   │
│                     │  MCP PROTOCOL        │                   │
│                     │                      │                   │
│                     │ Transporte:          │                   │
│                     │ Hermes Agent ◄──►  API                   │
│                     │                      │                   │
│                     │ Hermes usa skills +  │                   │
│                     │ prompts para navegar │                   │
│                     │ cada plataforma y su │                   │
│                     │ mecanismo de registro│                   │
│                     └──────────────────────┘                   │
│                                                                │
└──────────────────────────────────────────────────────────────────┘
```

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Lenguaje | Python 3.11+ |
| Browser Automation | Playwright (headless Chromium) |
| Backend | FastAPI + Uvicorn |
| Frontend | HTMX 1.9.12 + Vanilla JS + CSS (Dual Theme) |
| Base de datos | SQLite (WAL mode, row_factory) |
| Templates | Jinja2 |
| Tests | pytest + bats |
| Calidad | ruff + mypy |

## Módulos

### SCAN — Recolector híbrido (Script + Agente)

El módulo crítico del sistema. Conecta sitios web de vacantes, extrae listings, y almacena en SQLite con hash SHA-256 anti-duplicados.

**Dos estrategias:**

| Estrategia | Cuándo | Cómo |
|-----------|--------|------|
| **Script** | Sitios con patrones estables. Rápido, eficiente, desatendido. | Playwright ejecuta scripts directos (selectores CSS, navegación conocida) |
| **Agente** | El sitio cambió y el script falló. Hermes diagnostica, extrae, y actualiza. | Hermes Agent con prompts + skills. El agente "hereda" conocimiento previo |

**Si SCAN no funciona, el proyecto no tiene sentido.** Por eso la doble estrategia.

Scrapers actuales:
- **LinkedIn** — implementado y funcional vía script
- **Indeed, InfoJobs, Computrabajo, Tecnoempleo** — en roadmap

### DATA — Memoria personal

Almacena y reutiliza toda la información que los formularios de postulación solicitan:

- **Campos dinámicos** — nombre, email, teléfono, NIE, URL, fecha, etc. con validación por tipo
- **CV** — carga, previsualización y eliminación de PDF
- **Proveedores/Plataformas** — URLs de mis perfiles personales (mi LinkedIn, mi InfoJobs...)

**Auto-descubrimiento agentico**: Si Hermes encuentra un campo nuevo en un formulario (ej: "número de NIE"), lo agrega automáticamente en DATA. La próxima postulación ya lo tiene disponible. Esto es responsabilidad de Hermes, no del dashboard.

### STATUS / TABLE — Visor inteligente de ofertas

Muestra los datos que SCAN recolectó, con filtros de búsqueda, y **el estado de cada aviso**:

| Estado | Origen | Significado |
|--------|--------|-------------|
| ✅ Postulado | Auto-apply | Hermes se postuló exitosamente |
| 👤 Postulado manual | Usuario | Te postulaste desde el link "View" |
| ⏳ Pendiente | — | Está pendiente de postulación |
| ❌ Error | Auto-apply | Falló — requiere atención manual |
| ⚙️ Ajuste | Sistema | Requiere modificar parámetros |

El objetivo es informar rápidamente qué necesita atención y qué se procesó bien. Puedes abrir una oferta, postularte manualmente, y marcarla como 👤 Postulado.

### API — Interfaz REST para Hermes Agent

Puente entre el sistema y Hermes Agent. Expone las capacidades del sistema como endpoints REST:

- `GET /api/jobs` — buscar ofertas por estado, keywords, fecha
- `GET /api/status` — consultar estado de avisos
- `GET /api/data` — recuperar campos del perfil, CV, proveedores
- `POST /api/scan` — disparar un SCAN
- `POST /api/apply/result` — registrar resultado de auto-apply (✅ ❌)
- `POST /api/data/field` — agregar un campo nuevo descubierto por Hermes

### MCP Protocol — Transporte Hermes ↔ API

Capa de transporte que conecta Hermes Agent con la API del sistema. Hermes utiliza **skills y prompts** para:

- Navegar cada plataforma según su mecanismo de registro (cada una tiene el suyo)
- Ejecutar auto-apply desatendido
- Detectar cambios en los sitios y adaptarse
- Reportar resultados y campos faltantes
- **Intervenir los módulos**: si detecta patrones dinámicos usa skills; si puede automatizar sin skills, plasma los cambios directamente en scripts

**Hermes no es necesario para el funcionamiento del dashboard.** Puedes usar la herramienta completa sin el agente. Hermes es el multiplicador de poder — el componente agentico que permite la automatización real. El dashboard por sí solo **no tiene capacidad agentica**: consulta, filtra, y te deja postularte manualmente, pero depende de SCAN para tener ofertas.

### Dashboard — Shell visual

Interfaz web retro/pixel (Press Start 2P) que orquesta los módulos. **Sin capacidad agentica** — es puramente visual y de consulta. Depende de SCAN para tener ofertas que mostrar:

- Tabla de jobs con 9+ columnas, búsqueda cross-column, filtro por fecha y estado
- Paginación (10/50/100/250/All)
- SCAN button con barra de progreso + animación Dino
- Theme toggle dark/light (colores OpenCode TUI)
- DATA panel toggle (campos, CV, plataformas)
- Debug mode con STOP button
- Botón "View" para postularte manualmente + marcar como 👤 Postulado
- Diseño responsive completo (desktop → iPhone SE)
- Select/checkbox para acciones en lote

## Estado del proyecto

| Módulo | Estado | Prioridad |
|--------|--------|-----------|
| ✅ SCAN (LinkedIn vía script) | Funcional | 🔴 Crítica |
| ✅ DATA (campos, CV, proveedores) | Completo | Core |
| 🔄 STATUS/TABLE (visor + filtros + estados) | Por separar del dashboard | Alta |
| ❌ API (REST para Hermes) | No iniciado | Media |
| ❌ MCP Protocol (transporte) | No iniciado | Media |
| 🔄 Dashboard (shell visual) | Mejoras en curso + estado manual | Media |

## Empezar

```bash
git clone https://github.com/rbedani/devops.git
cd devops
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install
pytest
```

## Dashboard

```bash
# Modo producción
./scripts/dashboard.sh start

# Modo desarrollo (hot-reload)
./scripts/dashboard.sh dev

# Por defecto en http://127.0.0.1:3311
# Configurable via DASHBOARD_PORT
```

## Licencia

MIT

---

*Creado por Rodrigo Daniel Bedani — porque buscar trabajo no debería ser un trabajo de tiempo completo.*
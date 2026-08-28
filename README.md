# SAPI-Agent

Agente para monitoreo de marcas registradas en SAPI Venezuela
(Servicio Autónomo de la Propiedad Intelectual).

## ¿Qué hace?

Reduce de días a menos de 15 minutos el procesamiento del Boletín de
la Propiedad Industrial de Venezuela. Convierte PDFs estáticos en
inteligencia de mercado: detecta solicitudes similares a tu cartera
vigilada y alerta posibles conflictos en menos de 24 h tras la
publicación.

Detalles en [`docs/objetivos.md`](docs/objetivos.md).

## 📋 Especificaciones del proyecto

Las **especificaciones formales** del producto viven en
[`Specs/`](Specs/README.md):

| Doc | Contenido |
|---|---|
| [`00-overview.md`](Specs/00-overview.md) | Visión general, alcance, actores y roles |
| [`01-requisitos.md`](Specs/01-requisitos.md) | Requisitos funcionales (RF-NN) con estado |
| [`02-no-funcionales.md`](Specs/02-no-funcionales.md) | Requisitos no funcionales (RNF-NN) |
| [`03-restricciones.md`](Specs/03-restricciones.md) | Restricciones externas, técnicas y supuestos |
| [`04-arquitectura.md`](Specs/04-arquitectura.md) | Arquitectura de capas y flujo end-to-end |
| [`05-base-de-datos.md`](Specs/05-base-de-datos.md) | Esquema relacional (6 tablas) |
| [`06-api.md`](Specs/06-api.md) | Contrato REST + WebSocket (v0) |

Cada requisito lleva una columna **estado**: ✅ implementado, 🟡 parcial,
⬜ pendiente, 🚫 descartado.

## Arquitectura

```
PDF subido por usuario
  ↓
[API] guarda PDF + crea boletin status='extracting'
  ↓
[scripts/orchestration/processor.py] extrae texto con pdfplumber
  (fallback pymupdf) → boletin.extraction_json
  ↓
[API] marca needs_hermes_review=1 si hay páginas con imágenes
  ↓
[Hermes] lee SQLite → para páginas con imágenes usa LLM multimodal
  ↓
[Hermes] POST /api/boletines/{id}/structured con JSON normalizado
  ↓
[API] valida (Pydantic, EstatusLiteral), persiste, corre matcher
  (exacto+fuzzy+fonético, con cruce de clase Niza),
  envía email si hay coincidencias, expone en dashboard
  ↓
[Dashboard] UI multi-tenant + admin de usuarios + módulo de monitoreo
```

Detalle en [`Specs/04-arquitectura.md`](Specs/04-arquitectura.md).

## Capas

| Capa | Carpeta | Stack | Fase |
|---|---|---|---|
| Procesamiento | `scripts/` | Python 3.14, pdfplumber, pymupdf, rapidfuzz, jellyfish | 2 |
| API | `api/` | FastAPI, SQLite, JWT, Pydantic, WebSocket | 3 |
| Dashboard | `dashboard/` | React 19 + TypeScript + Vite + Tailwind + Zustand | 4 |
| Orquestador | `hermes/` | Hermes Agent (CLI ya instalada) | 5 |
| CI/CD | `.github/workflows/` | GitHub Actions (CI + CD pull-based) | 6 |
| Specs | `Specs/` | Documentación de requisitos (00-06) | — |

## Estructura

```
SAPI-Agent/
├── README.md                  # este archivo
├── AGENTS.md                  # guía para sesiones de OpenCode
├── .env.example               # plantilla de configuración
├── requirements.txt           # deps runtime (Python)
├── requirements-dev.txt       # deps dev (pytest)
├── .github/workflows/         # CI + CD
├── data/                      # SQLite + uploads + logs (gitignored)
├── docs/                      # objetivos, manuales operativos
├── Specs/                     # especificaciones formales (00-06)
├── hermes/                    # skill + cron + SOUL.md
├── scripts/                   # extracción, parsers, matcher, db, CLI
├── api/                       # FastAPI REST + WebSocket
├── dashboard/                 # SPA React + tests Vitest
└── tests/                     # pytest backend + Hermes (226 tests)
```

## Quickstart

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Inicializar BD (crea data/sapi.db + siembra admin si ADMIN_* están en .env)
cp .env.example .env
# editar .env: JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, SERVICE_TOKEN_HERMES
python -m scripts.cli init-db

# Arrancar API (modo dev)
uvicorn api.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs

# Dashboard (dev)
cd dashboard && npm install && npm run dev
# abre http://localhost:5173

# Tests
pytest tests/                                  # 226 tests backend + Hermes
cd dashboard && npm test                       # 37 tests Vitest
```

Más detalle en [`AGENTS.md`](AGENTS.md) (comandos, CI/CD, deploy,
logs).

## Estado

- **Fases 1-5** completas y desplegadas en producción
  ([`https://marcas.solutechve.net`](https://marcas.solutechve.net)).
- **CI/CD** con GitHub Actions (pull-based, ver
  [`AGENTS.md`](AGENTS.md#ci-githubworkflowsciyml)).
- **226 tests pytest + 37 tests Vitest**, todos verdes.
- **Specs/** documenta el estado real del proyecto (sincronizado con
  el código en cada release).

## Limitaciones

- **WEBPI requiere login + reCAPTCHA v3**: no se automatiza. La
  consulta de estatus de expedientes propios se nutre de los boletines
  que los usuarios suben al sistema.
- **WEBPI horario**: 8:00 AM – 11:30 PM hora Venezuela.
- Los PDFs de los boletines los comparten los usuarios del sistema;
  no se scrapean de `sapi.gob.ve`.
- **Solo español**: la UI, emails y mensajes están en español.
- **Solo email** para notificaciones (no SMS, no Slack, no push).

Detalle en [`Specs/03-restricciones.md`](Specs/03-restricciones.md).
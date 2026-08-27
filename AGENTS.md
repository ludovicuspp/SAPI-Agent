# AGENTS.md

Guía compacta para sesiones de OpenCode en este repositorio.

## Proyecto

SAPI-Agent: monitoreo de marcas registradas en SAPI Venezuela
(Servicio Autónomo de la Propiedad Intelectual). Detalle de
objetivos en [`docs/objetivos.md`](docs/objetivos.md).

## Idioma

- **Español** para documentación, comentarios, mensajes de error,
  emails y UI.
- **Inglés** para identificadores de código (Python/JS). Los strings
  visibles al usuario, en español.

## Estado actual del repo

El repo se construye por fases. Lo que **sí existe hoy** (Fase 4):

- `scripts/` — capa Python: extractores, parsers, matcher, db, CLI.
- `api/` — FastAPI REST API con auth JWT, CRUD multi-tenant,
  uploads + background tasks, WebSocket, structured (Hermes).
- `dashboard/` — SPA React (Vite + TS + Tailwind + Zustand) con
  login, summary, boletines, detecciones, watchlist, portfolio,
  users. 32 tests Vitest.
- `tests/` — pytest con fixtures (`tests/fixtures/sample_boletin.pdf`,
  `tests/conftest.py::tmp_db`). 140 tests.
- `hermes/SOUL.md` — solo manifiesto (sin skills todavía).

Lo que **aún no existe** (no inventes estructura):

- Otros skills de Hermes más allá de `sapi-monitor`.
- No hay `pyproject.toml`, ni config de `ruff`/`mypy`/`black`, ni
  pre-commit, ni CI. Si necesitas uno, pregunta antes de añadir.

## Fase 5 — Skill Hermes `sapi-monitor`

Orquesta la revisión visual de boletines con `needs_hermes_review=1`
(páginas con imágenes o encoding roto). Vive en
`hermes/skills/sapi-monitor/`:

| Archivo | Función |
|---|---|
| `SKILL.md` | Frontmatter Hermes + flujo operacional (decide visión vs texto) |
| `watchdog.sh` | Monitor estable para el cron (no imprime timestamps) |
| `scripts/pending_boletines.py` | Lista pendientes (CLI, usable como watchdog) |
| `scripts/db_utils.py` | Lectura read-only de `data/sapi.db` |
| `scripts/extract_page.py` | Texto de una página o render a PNG |
| `scripts/submit.py` | POST entries a `/api/boletines/{id}/structured` |
| `tests/` | 22 tests pytest |

**Ejecución como archivo** (no como paquete; el directorio lleva
guion y no es importable):

```bash
python hermes/skills/sapi-monitor/scripts/pending_boletines.py [--db data/sapi.db]
python hermes/skills/sapi-monitor/scripts/extract_page.py --pdf X.pdf --page N [--render DIR]
python hermes/skills/sapi-monitor/scripts/submit.py --boletin-id 1 --entries e.json
```

`submit.py` usa la stdlib (`urllib`) por defecto → **no añade
dependencias** y no falla por falta de `httpx`.

**Regla clave**: la skill solo **lee** la BD y **no calcula
similitudes**. El endpoint `structured.py` hace matching en Python y
marca `hermes_processed_at` (defensa contra duplicados).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt      # pytest + pytest-asyncio
cp .env.example .env                     # editar JWT_SECRET y credenciales
```

- `.env` vive en la **raíz del repo** (`scripts/config.py:14-29` lo
  lee con `pydantic-settings`). Si lo pones en `scripts/`, no se carga.
- `JWT_SECRET` con el valor por defecto emite `warnings.warn` al
  instanciar `Settings` (`scripts/config.py:60-70`). Genera uno real
  con `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- `init-db` siembra el usuario admin inicial si `ADMIN_EMAIL` y
  `ADMIN_PASSWORD` están definidos en `.env` y no hay admins
  (`scripts/cli.py:82-108`).

## Comandos

| Capa | Comando | Notas |
|---|---|---|
| Crear esquema | `python -m scripts.cli init-db` | idempotente; crea `data/sapi.db` |
| Crear usuario | `python -m scripts.cli create-user --email ... --role admin\|agent` | pide contraseña por TTY salvo `--password` |
| Procesar PDF | `python -m scripts.cli process-boletin PATH --user-email ... [--notify]` | pipeline end-to-end |
| Listar detecciones | `python -m scripts.cli list-detections --user-email ...` | |
| Digest por email | `python -m scripts.cli send-digest --user-email ...` | requiere SMTP configurado |
| Arrancar API | `uvicorn api.main:app --reload --port 8000` | dev; Swagger: `http://localhost:8000/docs` |
| Build Dashboard | `cd dashboard && npm run build` | genera `dashboard/dist/`; la API lo sirve en prod (SPA) |
| Arrancar Dashboard (dev) | `cd dashboard && npm run dev` | Vite en `:5173`; proxy `/api` y `/ws` → `:8000` |
| Arrancar API (prod) | `uvicorn api.main:app --host 127.0.0.1 --port 8000` | sirve `dist/` si existe; detrás de reverse proxy |
| Tests API | `pytest tests/` | o un archivo: `pytest tests/test_api.py` |
| Tests Dashboard | `cd dashboard && npm test` | o watch: `cd dashboard && npm run test:watch` |

## Publicación del dashboard

- El dashboard se compila a estático y FastAPI lo sirve en el mismo
  proceso. **Sin nginx/caddy local**: la SPA la sirve `api/main.py`
  (`_mount_dashboard`), montando `/assets` como estático y devolviendo
  `index.html` como fallback SPA para toda ruta que no empiece por
  `api/`, `docs`, `openapi.json` o `redoc`.
- En **producción** el dashboard usa URLs relativas para hablar con la
  API y el WebSocket (`/api` y `/ws`, mismo origen). Se definen en
  `dashboard/.env.production` y se inyectan al build con
  `VITE_API_BASE_URL=/api` / `VITE_WS_BASE_URL=/ws`. El CORS solo
  necesita el dominio público (`API_CORS_ORIGINS` en `.env` raíz).
- En **desarrollo** `dashboard/.env` apunta a `http://localhost:8000` /
  `ws://localhost:8000` y Vite proxifica `/api` y `/ws` a FastAPI.
- Pasos para desplegar: `cd dashboard && npm run build` y reiniciar la
  API (`uvicorn api.main:app --host 127.0.0.1 --port 8000`). Si `dist/`
  no existe, la SPA devuelve 503 con mensaje claro; la API sigue viva.

Si SMTP no está configurado, `send-digest` imprime el HTML en pantalla
en vez de enviarlo (`scripts/cli.py:297-301`).

## Convenciones clave

- **Multi-tenant**: `watchlist`, `portfolio`, `boletines`,
  `detections` tienen `user_id`. La capa actual pasa `user_id`
  explícitamente a las funciones de `scripts/db.py`. Cuando exista la
  API, filtrará por `current_user.id` salvo rol `admin`.
- **Hoy el writer es el CLI**, no la API (la API no existe todavía).
  El principio "single writer en SQLite" se materializará en Fase 3.
- **Match scores siempre en Python** (`scripts/matcher/`): exact,
  fuzzy (rapidfuzz), phonetic (jellyfish), combinados. Hermes y el
  LLM solo extraen campos; nunca calculan similitud.
- **Trazabilidad de detections**: cada fila guarda
  `source ∈ {pdfplumber_text, hermes_llm, hermes_vision}` y
  `confidence ∈ {high, medium, low}`. No inventes otros valores.
- **Patrones de parser**: las entradas del boletín se reconocen por
  patrón A/B/C, definidos en `scripts/parsers/patterns/`. Añadir un
  patrón nuevo requiere también su test en `tests/test_patterns.py`.

## No hacer

- No scrapear `sapi.gob.ve`; los boletines los suben los usuarios.
- No automatizar login a WEBPI (reCAPTCHA v3).
- No escribir en SQLite desde Hermes; siempre vía API (cuando exista).
- No añadir dependencias fuera de `requirements.txt` /
  `requirements-dev.txt` / `dashboard/package.json` sin pedirlo.
- No commitear `.env`, `data/sapi.db*`, ni PDFs en `data/uploads/`
  (ya está en `.gitignore`).
- No crear `api/`, `dashboard/`, ni poblar `hermes/skills/` por tu
  cuenta: pregunta primero qué fase toca.

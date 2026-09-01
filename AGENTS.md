# AGENTS.md

Guía compacta para OpenCode. Producto: `docs/objetivos.md`. Contrato: `Specs/`.

## Proyecto

Monitoreo de marcas SAPI Venezuela. Fases 1–5 en prod
(`https://marcas.solutechve.net`): Caddy del proveedor →
`sapi-api.service` (`0.0.0.0:8000`).

## Idioma

- Español: docs, comentarios, errores, emails, UI.
- Inglés: identificadores Python/JS.

## Layout

| Path | Qué es |
|---|---|
| `scripts/` | Core: `cli.py`, `db.py`, `config.py`, `schemas.py`, `auth.py`. Subdirs: `extractors/`, `parsers/` (A/B/C + `patterns/`), `matcher/`, `orchestration/`, `notifiers/` |
| `api/` | FastAPI. Schemas en `scripts/schemas.py`, no en `api/` |
| `dashboard/` | Vite + React 19 + TS. Alias `@` → `src/` |
| `hermes/skills/sapi-monitor/` | Única skill Hermes; no inventar otras |
| `tests/` | pytest. PDF sintético: `tests/fixtures/sample_boletin.pdf` |
| `Specs/` | Requisitos con estado real; no duplicar aquí |

No hay `pyproject.toml`, ruff, mypy, black ni pre-commit.
**Pregunta antes de añadirlos.**

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # raíz del repo, NO scripts/
python -m scripts.cli init-db
```

- `.env` lo lee `scripts/config.py` desde `REPO_ROOT/.env`.
- `JWT_SECRET` default emite `warnings.warn`.
- `init-db` siembra admin si `ADMIN_EMAIL`+`ADMIN_PASSWORD` y no hay admins.
- Local: Python 3.14. **CI usa 3.12** (wheels nativos fallan en 3.14).
- Dev: `httpx2` en `requirements-dev.txt` (no añadir `httpx`).

## Comandos

| Qué | Comando |
|---|---|
| Schema | `python -m scripts.cli init-db` |
| Usuario | `python -m scripts.cli create-user --email … --role admin\|agent` |
| Watchlist | `python -m scripts.cli add-watchlist --user-email … --name … [--class-nice N]` |
| Portfolio | `python -m scripts.cli add-portfolio --user-email … --name … [--expediente …]` |
| Listar WL | `python -m scripts.cli list-watchlist --user-email … [--only-active]` |
| Listar PF | `python -m scripts.cli list-portfolio --user-email …` |
| Detecciones | `python -m scripts.cli list-detections --user-email … [--limit N]` |
| PDF e2e | `python -m scripts.cli process-boletin PATH --user-email … [--notify]` |
| Digest | `python -m scripts.cli send-digest --user-email …` |
| Stats | `python -m scripts.cli stats --user-email …` |
| API dev | `uvicorn api.main:app --reload --port 8000` |
| API prod | unidad `sapi-api.service` (no adivinar el binario) |
| Dash dev | `cd dashboard && npm run dev` (`:5173`; proxy `/api` → `:8000`) |
| Dash build | `cd dashboard && npm run build` → `dashboard/dist/` (incluye `tsc -b`) |
| Tests API | `pytest tests/` o `pytest tests/test_api.py` |
| Tests Hermes | `pytest hermes/skills/sapi-monitor/tests` |
| Tests UI | `cd dashboard && npm test` |
| Tests UI (watch) | `cd dashboard && npm run test:watch` |

SMTP ausente: `send-digest` imprime el HTML y no envía.

## Tests — trampas

- `get_settings` está en `lru_cache`: en tests que tocan env,
  `get_settings.cache_clear()` al entrar y al salir (ver
  `tests/test_api.py`).
- Fixture `tmp_db` = SQLite temporal. Hermes tests también; **no**
  requieren `data/sapi.db`.
- `tests/test_pipeline_e2e.py` **skipea** si no está
  `data/uploads/BPI 654 listo.pdf` (gitignored). En CI suele skippearse.
- Dashboard: Vitest + jsdom; setup en `dashboard/vitest-setup.ts`
  (polyfill localStorage para Node 26+).

## Hermes `sapi-monitor`

Directorio con guion: **ejecutar como archivo**, no como paquete.
Bootstrap de `sys.path` en `scripts/_bootstrap.py`.

```bash
python hermes/skills/sapi-monitor/scripts/pending_boletines.py [--db data/sapi.db]
python hermes/skills/sapi-monitor/scripts/extract_page.py --pdf X.pdf --page N [--render DIR]
python hermes/skills/sapi-monitor/scripts/submit.py --boletin-id 1 --entries e.json
```

- `submit.py` usa `urllib` (stdlib). Header `X-Hermes-Token` =
  `SERVICE_TOKEN_HERMES`. Token vacío → API 503.
- Skill **solo lee** SQLite. Matching y persistencia:
  `POST /api/boletines/{id}/structured` (máx. 100 entries; top-5
  matches; si `hermes_processed_at` → `already_processed`).
- Watchdog: stdout **estable** (sin timestamps). Hermes rechaza
  symlinks fuera de `~/.hermes/scripts/` → **copiar** `watchdog.sh`,
  no enlazar. Detalle en `hermes/skills/sapi-monitor/SKILL.md`.

## Dashboard servido por FastAPI

`api/main.py` monta `dashboard/dist/` (`/assets` + fallback SPA).
Rutas que no intercepta: `api/`, `docs`, `openapi.json`, `redoc`.
Sin `dist/` → SPA 503; la API sigue.

- Prod: `dashboard/.env.production` deja `VITE_API_BASE_URL=` **vacío**.
  Los fetches ya van a `/api/...`; un base `/api` duplica el prefijo.
  `dashboard/.env` está gitignored; `.env.production` sí se commitea.
  Documentación del gotcha: `dashboard/.env.example`.
- WS: `wsBase()` = origen de la página.
  Path real: `/api/boletines/ws/{id}`. El proxy Vite `/ws` es residual.
- Alias `/api/v0/*` → `/api/*` en `api/middleware.py` (ASGI puro).
  **No** uses `BaseHTTPMiddleware` (rompe con Starlette + Py 3.12+).

## CI / CD

`.github/workflows/ci.yml` (trackeado): push/PR a `main`. Python 3.12,
Node 22. Backend = pytest partido en steps; dashboard = `npm ci`,
`npm run build` (`tsc -b`), `npm test`. Artefacto `dist/` obligatorio.

`.github/workflows/cd.yml`: espera 60 s y hace curl al health público.
**No despliega.** El deploy es pull-based (SSH público no llega a esta VM;
secrets `SSH_*` no se usan):

- `sapi-pull.timer` — **user** systemd, cada 5 min, `Linger=yes`.
  Estado: `systemctl --user status sapi-pull.timer`.
- `scripts/pull_deploy.sh` — `git pull --ff-only`, pip, dashboard
  build, `sudo -n systemctl restart sapi-api.service`, health local.
  Log: `/var/log/sapi-pull.log`. Lock: `/home/luisv/data/sapi-pull.lock`.
- Manual: `bash scripts/pull_deploy.sh`.
- Unidades de referencia en `scripts/systemd/`; la API de prod es la
  unidad **system** `sapi-api.service` (`EnvironmentFile` = `.env` raíz).
  No arrancar el leftover `~/.config/systemd/user/sapi-agent.service`.

## Proxy (uploads grandes)

Caddy del proveedor termina TLS y hace `reverse_proxy 127.0.0.1:8000`.
El `Caddyfile` **no vive en el repo** (está en el panel del proveedor,
ver `Specs/07-proxy.md`). Subir PDFs de `MAX_UPLOAD_MB=300` requiere
`max_size 300MB` + timeouts `600s` en el proxy; sin eso, subidas
grandes (`file.read()` con pdfplumber sobre PDFs de 1000+ páginas)
reciben 413/504. No asumas que tocar la API basta: 413/504 en prod
suele ser cap del proxy, no del backend.

## Convenciones

- Multi-tenant: `watchlist` / `portfolio` / `detections` tienen
  `user_id`. **`boletines` usa `uploaded_by`**, no `user_id`.
  API filtra por `current_user.id` salvo rol `admin`.
- Una sola capa de datos: `scripts/db.py`. CLI y API escriben ahí
  (`api/deps.py::get_db` = una conexión por request).
- SQLite con `check_same_thread=False` (threadpool de uvicorn).
- Scores **siempre** en `scripts/matcher/`. Si ambos `class_nice`
  están definidos y difieren → no-match. Hermes/LLM no calculan similitud.
- `source ∈ {pdfplumber_text, hermes_llm, hermes_vision}`,
  `confidence ∈ {high, medium, low}`,
  `match_kind ∈ {similar, own_status}`,
  `role ∈ {admin, agent}`. Estatus: `EstatusLiteral` en
  `scripts/schemas.py`. No inventes valores.
- Dedupe detections: UNIQUE `(boletin_id, expediente, watchlist_id)`.
- Patrón de parser nuevo → `scripts/parsers/patterns/` + test en
  `tests/test_patterns.py`.

## No hacer

- No scrapear `sapi.gob.ve`. No automatizar WEBPI (reCAPTCHA v3).
- No escribir SQLite desde Hermes; siempre el POST `structured`.
- No añadir deps fuera de `requirements.txt` /
  `requirements-dev.txt` / `dashboard/package.json` sin pedirlo.
- No commitear `.env`, `data/sapi.db*`, PDFs en `data/uploads/`, ni
  `data/checkpoints/` (checkpoints de extracción por lotes).
- No crear skills Hermes extra ni tooling Python de lint/format
  sin preguntar.

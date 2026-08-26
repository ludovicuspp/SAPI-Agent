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

El repo se construye por fases. Lo que **sí existe hoy** (Fase 2):

- `scripts/` — capa Python: extractores, parsers, matcher, db, CLI.
- `tests/` — pytest con fixtures (`tests/fixtures/sample_boletin.pdf`,
  `tests/conftest.py::tmp_db`).
- `hermes/SOUL.md` — solo manifiesto (sin skills todavía).

Lo que **aún no existe** (no inventes estructura):

- `api/` está **vacío** (Fase 3).
- `dashboard/` no existe (Fase 4).
- `hermes/skills/` está vacío (Fase 5).
- No hay `pyproject.toml`, ni config de `ruff`/`mypy`/`black`, ni
  pre-commit, ni CI. Si necesitas uno, pregunta antes de añadir.

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
| Tests | `pytest tests/` | o un archivo: `pytest tests/test_matchers.py` |

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

# AGENTS.md

Instrucciones para agentes AI que trabajen en este repositorio.

## Proyecto

SAPI-Agent: agente para monitoreo de marcas registradas en SAPI
(Servicio Autónomo de la Propiedad Intelectual), Venezuela. Detalle
de objetivos en [`docs/objetivos.md`](docs/objetivos.md).

## Idioma

Toda la documentación, comentarios de código, mensajes de error,
emails y UI están en **español**. Los identificadores de código
(Python, JS) van en inglés por convención; los strings visibles al
usuario, en español.

## Capas y sus comandos

| Capa | Setup | Desarrollo | Tests |
|---|---|---|---|
| Python (todo) | `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` | — | `pytest tests/` |
| `scripts/` | (hereda) | `python -m scripts.cli <subcmd>` | `pytest tests/test_matchers.py tests/test_db.py` |
| `api/` | (hereda) | `uvicorn api.main:app --reload --port 8000` | `pytest tests/test_api.py` |
| `dashboard/` | `cd dashboard && npm install` | `npm run dev` | — |
| `hermes/` | — | `hermes skills list`, `hermes cron list` | manual |

## Convenciones

- **Multi-tenant**: cada marca vigilada, portafolio, boletín y
  detection tiene `user_id`. La API filtra por `current_user.id`
  salvo rol `admin`. Ver `api/core/tenancy.py` (Fase 3).
- **Single writer en SQLite**: solo la API escribe. Hermes lee y
  postea vía `/api/structured`. No hay escrituras concurrentes.
- **Match scores son siempre Python**: ni Hermes ni el LLM calculan
  similitud. Hermes devuelve campos (`marca`, `titular`, etc.) y el
  motor `scripts/matcher/` calcula el score.
- **Trazabilidad**: cada `detection` guarda `source ∈ {pdfplumber_text,
  hermes_llm, hermes_vision}` y `confidence ∈ {high, medium, low}`.

## Estructura

Ver `README.md`. Las carpetas `scripts/`, `api/`, `dashboard/`, `tests/`
llegan en Fases 2-4. Si necesitas modificarlas y todavía no existen,
primero pregunta antes de inventar el orden.

## No hacer

- No scrapear `sapi.gob.ve`. Los boletines los suben los usuarios.
- No automatizar login a WEBPI (reCAPTCHA v3).
- No escribir en SQLite desde Hermes; siempre vía API.
- No instalar dependencias no listadas en `requirements.txt` /
  `dashboard/package.json` sin pedirlo.
- No commitear `.env`, `data/sapi.db*`, ni PDFs en `data/uploads/`.

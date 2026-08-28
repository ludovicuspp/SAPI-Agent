# 04 — Arquitectura

## Visión general

```
┌─────────────────────────────────────────────────────────────────┐
│                       Usuario (navegador)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│   Caddy externo del proveedor (TLS termination, reverse proxy)  │
│   marcas.solutechve.net:443 → proxy_pass → 127.0.0.1:8000      │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (loopback VM)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│            FastAPI (uvicorn, sapi-api.service)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ routers/  auth, users, watchlist, portfolio, boletines, │  │
│  │           detections, uploads, structured, summary       │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ deps.py    get_db, get_current_user, require_hermes      │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ schemas.py Pydantic models (entrada/salida)             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│  ┌──────────────────────────┴───────────────────────────────┐  │
│  │ scripts/                                                 │  │
│  │   extractors/   pdf_text, pdf_meta                       │  │
│  │   parsers/      boletin_header, marca_entry (A/B/C)      │  │
│  │   matcher/      exact, fuzzy, phonetic, combined         │  │
│  │   notifiers/    email_smtp                              │  │
│  │   orchestration/ processor.process_pdf                   │  │
│  │   db.py         SQLite CRUD                             │  │
│  └─────────────────────────────────────────────────────────┘  │
└────────────────┬───────────────────────────┬────────────────────┘
                 │                           │
                 ▼                           ▼
   ┌──────────────────────────┐  ┌──────────────────────────────┐
   │  data/sapi.db (SQLite)   │  │  data/uploads/*.pdf          │
   │  FK, UNIQUE, check_same_ │  │  (gitignored)                │
   │  thread=False            │  └──────────────────────────────┘
   └──────────────────────────┘
                 ▲
                 │  lectura (read-only)
                 │
┌─────────────────────────────────────────────────────────────────┐
│           Hermes (orquestador externo, cron-driven)             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  skills/sapi-monitor/                                    │  │
│  │    watchdog.sh        → SIN_PENDIENTES (hash estable)   │  │
│  │    pending_boletines.py → lista boletines con needs_    │  │
│  │                          hermes_review=1                │  │
│  │    extract_page.py    → texto o render PNG por página   │  │
│  │    submit.py          → POST /api/boletines/{id}/       │  │
│  │                         structured                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│   (LLM decide: visión vs texto; entrega entries normalizadas)  │
└─────────────────────────────────────────────────────────────────┘
```

## Flujo end-to-end de un boletín

```
1. Usuario sube PDF
   POST /api/boletines/upload (multipart, MAX_UPLOAD_MB=300)
   │
   ├── Crea fila en `boletines` con status='extracting'
   └── Background task: processor.process_pdf()
       │
       ├── pdfplumber extrae texto (fallback pymupdf si cid:)
       ├── boletin_header detecta metadatos
       ├── MarcaEntryParser detecta entradas (patrones A/B/C)
       ├── has_images | low_confidence ⇒ needs_hermes_review=1
       ├── score_pair() vs cada watchlist + portfolio
       ├── detections_add() (con UNIQUE INDEX dedupe)
       ├── status='extracted'
       └── send_detection_emails() si SMTP configurado

2. Si needs_hermes_review=1:
   cron de Hermes ejecuta watchdog.sh
   → pending_boletines.py lista pendientes
   → Para cada boletín: extract_page.py por página
   → LLM decide visión vs texto
   → LLM entrega entries (StructuredEntryIn)
   → POST /api/boletines/{id}/structured (header X-Hermes-Token)
       │
       ├── require_hermes valida token
       ├── Para cada entry: score_pair() vs todas las watchlists
       │   (cap top-5 por similitud)
       ├── detections_add() (INSERT OR IGNORE por dedupe)
       ├── portfolio_update_status() si expediente match
       └── UPDATE boletines SET hermes_processed_at=now()
```

## Decisiones arquitectónicas clave

### DA-01 — Una sola capa de escritura a BD

`scripts/db.py` es la **única** capa que escribe en `data/sapi.db`.
CLI y API la usan. **Hermes solo lee**. Para que Hermes modifique
estado, debe llamar al endpoint `POST /api/boletines/{id}/structured`.

### DA-02 — Matching siempre en Python

Ningún componente LLM calcula similitud. El LLM solo extrae campos
de cada entrada (marca, titular, expediente, clase, estatus). El
matching es siempre:

```python
score_pair(watch_name, candidate) → MatchResult(
    is_match, similarity, method, confidence
)
```

Combinado: exact (1.0/high) → fuzzy (rapidfuzz, 0.80+) → fonético
(jellyfish, idéntico=0.70/medium) → no-match.

### DA-03 — Defensa contra duplicados (Hermes)

`hermes_processed_at` se setea tras el primer POST exitoso.
Re-POSTs devuelven `status="already_processed"` sin tocar nada.

### DA-04 — Trazabilidad de detections

Cada fila guarda:

- `source ∈ {pdfplumber_text, hermes_llm, hermes_vision}` — quién
  extrajo la entrada.
- `confidence ∈ {high, medium, low}` — confianza del extractor.
- `match_kind ∈ {similar, own_status}` — match contra watchlist o
  contra portfolio propio por expediente.
- `pais`, `fecha_inscripcion`, `fuente_parsing`, `es_figura`,
  `es_lema`, `raw_excerpt` — campos de trazabilidad.

### DA-05 — Multi-tenant por `user_id`

`watchlist`, `portfolio`, `boletines`, `detections` tienen
`user_id NOT NULL`. La API filtra por `current_user.id` salvo que
el rol sea `admin` (ve todo).

### DA-06 — Pull-based deploy (no SSH)

El SSH público no alcanza la VM (puerto 22 responde otro host del
proveedor). El CD es pull-based:

- Push a `main` → GitHub Actions corre CI + smoke-test.
- En la VM, `sapi-pull.timer` (user systemd, cada 5 min, Linger=yes)
  ejecuta `scripts/pull_deploy.sh`.
- El script hace `git pull --ff-only`, `npm ci && npm run build`,
  `pip install -r requirements.txt`, `systemctl restart sapi-api`,
  y verifica `curl 127.0.0.1:8000/api/health`.

## Patrones de diseño

| Patrón | Aplicación |
|---|---|
| Repository | `scripts/db.py` abstrae todas las queries |
| Strategy | `scripts/matchers/combined.py` orquesta los 3 métodos |
| State machine | `boletines.status`: pending → extracting → extracted → hermes_pending → hermes_done / failed |
| Background task | FastAPI `BackgroundTasks` para procesar PDF sin bloquear upload |
| Webhook-style | `require_hermes` valida el header `X-Hermes-Token` |
| Idempotency key | `INSERT OR IGNORE` + UNIQUE INDEX sobre `(boletin_id, expediente, watchlist_id)` |
| Defense in depth | Pydantic valida + UNIQUE INDEX + cap top-5 + `EstatusLiteral` enum + `INSERT OR IGNORE` (anti-alucinación) |

## Concurrencia

- **FastAPI** corre en uvicorn (multi-thread por defecto).
- **SQLite** con `check_same_thread=False` para soportar el threadpool.
- **`sapi-pull.timer`** con `LOCK_FILE` para evitar carreras si dos
  triggers se solapan.
- **No hay race conditions** porque el pipeline es single-writer
  por boletín (cada `boletin_id` se procesa una vez).
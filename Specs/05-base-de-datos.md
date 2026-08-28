# 05 — Base de datos

SQLite (`data/sapi.db`). 6 tablas: `users`, `watchlist`, `portfolio`,
`boletines`, `detections`, `scans_log`. Esquema extraído de
`scripts/db.py:21-130`.

## users

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,           -- bcrypt
    role TEXT NOT NULL CHECK (role IN ('admin','agent')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## watchlist

```sql
CREATE TABLE watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    class_nice INTEGER,                    -- opcional, 1-45 si está
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, name)                  -- no duplicar nombre por usuario
);
CREATE INDEX idx_watchlist_user ON watchlist(user_id);
```

## portfolio

```sql
CREATE TABLE portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    expediente TEXT,                       -- opcional, búsqueda por match exacto
    class_nice INTEGER,
    status TEXT,                           -- estatus SAPI (EstatusLiteral)
    last_checked_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_portfolio_user ON portfolio(user_id);
CREATE INDEX idx_portfolio_expediente ON portfolio(expediente);
```

## boletines

```sql
CREATE TABLE boletines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,               -- ruta absoluta al PDF en data/uploads/
    file_sha256 TEXT NOT NULL,             -- hash para dedupe
    bulletin_number INTEGER,               -- ej. 654
    period TEXT,                           -- ej. "2026-02"
    pages INTEGER,                         -- total de páginas del PDF
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','extracting','extracted',
                          'hermes_pending','hermes_done','failed')),
    extraction_json TEXT,                  -- JSON con pages[] y metadata
    needs_hermes_review INTEGER NOT NULL DEFAULT 0,  -- 0/1
    hermes_processed_at TEXT,              -- NULL hasta que Hermes postea
    hermes_error TEXT,
    error TEXT,                            -- error de extracción si status='failed'
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed_at TEXT,
    entries_matcheables INTEGER NOT NULL DEFAULT 0,
    entries_hermes_pending INTEGER NOT NULL DEFAULT 0,
    entries_figura INTEGER NOT NULL DEFAULT 0,
    entries_lema INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_boletines_status ON boletines(status);
CREATE INDEX idx_boletines_needs_hermes ON boletines(needs_hermes_review, hermes_processed_at);
```

## detections

```sql
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boletin_id INTEGER NOT NULL REFERENCES boletines(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    watchlist_id INTEGER REFERENCES watchlist(id) ON DELETE CASCADE,
    portfolio_id INTEGER REFERENCES portfolio(id) ON DELETE CASCADE,
    expediente TEXT,
    mark_name TEXT NOT NULL,
    titular TEXT,
    class_nice INTEGER,
    page INTEGER,
    similarity REAL NOT NULL,
    match_kind TEXT NOT NULL
        CHECK (match_kind IN ('similar','own_status')),
    source TEXT NOT NULL
        CHECK (source IN ('pdfplumber_text','hermes_llm','hermes_vision')),
    confidence TEXT NOT NULL
        CHECK (confidence IN ('high','medium','low')),
    raw_excerpt TEXT,
    detected_at TEXT NOT NULL DEFAULT (datetime('now')),
    notified_email INTEGER NOT NULL DEFAULT 0,
    notified_at TEXT,
    pais TEXT,
    fecha_inscripcion TEXT,
    fuente_parsing TEXT,                   -- 'python' | 'hermes'
    es_figura INTEGER NOT NULL DEFAULT 0,
    es_lema INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_detections_user ON detections(user_id);
CREATE INDEX idx_detections_boletin ON detections(boletin_id);
CREATE INDEX idx_detections_watchlist ON detections(watchlist_id);
CREATE UNIQUE INDEX idx_detections_dedupe
    ON detections(boletin_id, expediente, watchlist_id);
CREATE INDEX idx_detections_boletin_exp
    ON detections(boletin_id, expediente);
```

### Anti-alucinación: el UNIQUE INDEX

`idx_detections_dedupe` previene detecciones duplicadas cuando:

- Hermes Vision alucina y reenvía el mismo `expediente` varias veces.
- El mismo boletín se procesa dos veces por un fallo del cliente.
- Hay concurrencia y dos workers intentan insertar la misma fila.

`detections_add` usa `INSERT OR IGNORE` para que el segundo intento
simplemente no haga nada (sin error).

## scans_log

```sql
CREATE TABLE scans_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    kind TEXT NOT NULL
        CHECK (kind IN ('upload','extract','hermes','notify','match')),
    boletin_id INTEGER REFERENCES boletines(id),
    summary TEXT,
    status TEXT NOT NULL CHECK (status IN ('ok','error')),
    detail TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_scans_log_boletin ON scans_log(boletin_id);
CREATE INDEX idx_scans_log_created ON scans_log(created_at);
```

## Relaciones

```
users ──┬── watchlist (1:N)
        ├── portfolio (1:N)
        ├── boletines (1:N via uploaded_by)
        └── detections (1:N)

boletines ──┬── detections (1:N via boletin_id)
            └── scans_log (1:N via boletin_id)

watchlist ──── detections (1:N via watchlist_id, ON DELETE CASCADE)
portfolio ──── detections (1:N via portfolio_id, ON DELETE CASCADE)
```

## Migración

- El esquema se crea con `python -m scripts.cli init-db` (idempotente).
- `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` /
  `CREATE UNIQUE INDEX IF NOT EXISTS` para todos los objetos.
- Añadir nueva tabla/columna: editar `scripts/db.py`, hacer commit,
  y `init-db` la aplica sin romper.
- **No** usamos Alembic ni Flyway (decisión: proyecto single-node,
  SQLite, deploy simple). Si en el futuro se migra a Postgres,
  evaluar Alembic.

## Datos de ejemplo

Tras `init-db`, la BD contiene solo el usuario admin (sembrado por
`ADMIN_EMAIL`/`ADMIN_PASSWORD`). Hoy no hay seeders de watchlist
ni portfolio; cada usuario los crea desde el dashboard.
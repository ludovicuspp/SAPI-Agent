"""Capa de persistencia SQLite.

Cada "tabla" se expone como submódulo con funciones puras que reciben
``conn`` como primer argumento. Esto facilita la inyección en tests
y respeta el principio de "single writer" (en Fase 3 la API asumirá
el rol de único escritor; esta capa expone también un writer directo
para que el CLI de Fase 2 funcione antes de tener API).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','agent')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    class_nice INTEGER,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);

CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    expediente TEXT,
    class_nice INTEGER,
    status TEXT,
    last_checked_at TEXT,
    notes TEXT,
    pais TEXT NOT NULL DEFAULT 'Venezuela',
    etiqueta TEXT,
    tipo_registro TEXT,
    bufete TEXT,
    solicitud TEXT,
    fecha_solicitud TEXT,
    registro TEXT,
    fecha_registro TEXT,
    fecha_vencimiento TEXT,
    titular TEXT,
    tramitante TEXT,
    empresa_licenciada TEXT,
    productos_servicios TEXT,
    comentarios TEXT,
    last_boletin_id INTEGER REFERENCES boletines(id),
    last_boletin_period TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_expediente ON portfolio(expediente);
CREATE INDEX IF NOT EXISTS idx_portfolio_registro ON portfolio(registro);
CREATE INDEX IF NOT EXISTS idx_portfolio_solicitud ON portfolio(solicitud);

CREATE TABLE IF NOT EXISTS portfolio_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    boletin_id INTEGER REFERENCES boletines(id) ON DELETE SET NULL,
    boletin_period TEXT,
    boletin_number INTEGER,
    estado TEXT,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_portfolio_history_portfolio ON portfolio_history(portfolio_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_history_dedupe
    ON portfolio_history(portfolio_id, boletin_id) WHERE boletin_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS boletines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    bulletin_number INTEGER,
    period TEXT,
    pages INTEGER,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','extracting','extracted',
                          'hermes_pending','hermes_done','failed')),
    extraction_json TEXT,
    needs_hermes_review INTEGER NOT NULL DEFAULT 0,
    hermes_processed_at TEXT,
    hermes_error TEXT,
    error TEXT,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed_at TEXT,
    entries_matcheables INTEGER NOT NULL DEFAULT 0,
    entries_hermes_pending INTEGER NOT NULL DEFAULT 0,
    entries_figura INTEGER NOT NULL DEFAULT 0,
    entries_lema INTEGER NOT NULL DEFAULT 0,
    progress_step TEXT,
    progress_current_page INTEGER,
    progress_total_pages INTEGER
);
CREATE INDEX IF NOT EXISTS idx_boletines_status ON boletines(status);
CREATE INDEX IF NOT EXISTS idx_boletines_needs_hermes
    ON boletines(needs_hermes_review, hermes_processed_at);

CREATE TABLE IF NOT EXISTS detections (
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
    needs_hermes_reverify INTEGER NOT NULL DEFAULT 0,
    notified_email INTEGER NOT NULL DEFAULT 0,
    notified_at TEXT,
    pais TEXT,
    fecha_inscripcion TEXT,
    fuente_parsing TEXT,
    es_figura INTEGER NOT NULL DEFAULT 0,
    es_lema INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_detections_user ON detections(user_id);
CREATE INDEX IF NOT EXISTS idx_detections_boletin ON detections(boletin_id);
CREATE INDEX IF NOT EXISTS idx_detections_watchlist ON detections(watchlist_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_detections_dedupe
    ON detections(boletin_id, expediente, watchlist_id);
CREATE INDEX IF NOT EXISTS idx_detections_boletin_exp
    ON detections(boletin_id, expediente);

CREATE TABLE IF NOT EXISTS scans_log (
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
CREATE INDEX IF NOT EXISTS idx_scans_log_boletin ON scans_log(boletin_id);
CREATE INDEX IF NOT EXISTS idx_scans_log_created ON scans_log(created_at);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Abre una conexión SQLite con FK activadas y row_factory.

    `check_same_thread=False`: cada request abre su propia conexión
    aislada (ver `get_db`), que se descarta al terminar; con WAL activo
    no hay estado compartido entre hilos, así que es seguro.
    """
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: str | Path) -> None:
    """Crea el esquema si no existe. Idempotente.

    Aplica también ``ALTER TABLE ADD COLUMN`` para añadir columnas que
    puedan faltar en bases de datos creadas con versiones anteriores
    (Fase 2 original). Esto permite actualizar la BD en caliente sin
    perder datos.

    Importante: las migraciones se aplican ANTES del ``SCHEMA_SQL``
    para que las columnas referenciadas por índices existan al
    ejecutar el script (e.g. ``idx_portfolio_registro``).
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        _migrate_add_columns(conn)
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def _migrate_add_columns(conn: sqlite3.Connection) -> None:
    """Añade columnas que pueden faltar en BD creadas con Fase 2.0.

    Usa try/except OperationalError para que sea idempotente: si la
    columna ya existe, SQLite devuelve un error que ignoramos.
    """
    migrations = [
        ("boletines", "entries_matcheables", "INTEGER NOT NULL DEFAULT 0"),
        ("boletines", "entries_hermes_pending", "INTEGER NOT NULL DEFAULT 0"),
        ("boletines", "entries_figura", "INTEGER NOT NULL DEFAULT 0"),
        ("boletines", "entries_lema", "INTEGER NOT NULL DEFAULT 0"),
        ("boletines", "progress_step", "TEXT"),
        ("boletines", "progress_current_page", "INTEGER"),
        ("boletines", "progress_total_pages", "INTEGER"),
        ("detections", "pais", "TEXT"),
        ("detections", "fecha_inscripcion", "TEXT"),
        ("detections", "fuente_parsing", "TEXT"),
        ("detections", "es_figura", "INTEGER NOT NULL DEFAULT 0"),
        ("detections", "es_lema", "INTEGER NOT NULL DEFAULT 0"),
        ("detections", "needs_hermes_reverify", "INTEGER NOT NULL DEFAULT 0"),
        # Portfolio ampliado (módulo portfolio: 17 campos + historial).
        ("portfolio", "pais", "TEXT NOT NULL DEFAULT 'Venezuela'"),
        ("portfolio", "etiqueta", "TEXT"),
        ("portfolio", "tipo_registro", "TEXT"),
        ("portfolio", "bufete", "TEXT"),
        ("portfolio", "solicitud", "TEXT"),
        ("portfolio", "fecha_solicitud", "TEXT"),
        ("portfolio", "registro", "TEXT"),
        ("portfolio", "fecha_registro", "TEXT"),
        ("portfolio", "fecha_vencimiento", "TEXT"),
        ("portfolio", "titular", "TEXT"),
        ("portfolio", "tramitante", "TEXT"),
        ("portfolio", "empresa_licenciada", "TEXT"),
        ("portfolio", "productos_servicios", "TEXT"),
        ("portfolio", "comentarios", "TEXT"),
        ("portfolio", "last_boletin_id", "INTEGER"),
        ("portfolio", "last_boletin_period", "TEXT"),
    ]
    for table, column, typedef in migrations:
        try:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {typedef}"
            )
        except sqlite3.OperationalError:
            # La columna ya existe; ignorar.
            pass
    # Índices por identidad (registro / solicitud) tras garantizar columnas.
    # Se hace aquí para que funcione en BD viejas que aún no tengan la
    # tabla portfolio (init_db corre migraciones ANTES del SCHEMA_SQL).
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_portfolio_registro ON portfolio(registro)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_solicitud ON portfolio(solicitud)",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Context manager para transacciones explícitas."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def row_to_dict(row: sqlite3.Row | None) -> Optional[dict[str, Any]]:
    return dict(row) if row is not None else None


# ── users ───────────────────────────────────────────────────────


@dataclass
class UserRow:
    id: int
    email: str
    password_hash: str
    role: str
    active: int
    created_at: str
    updated_at: str


def _user_from_row(row: sqlite3.Row) -> UserRow:
    return UserRow(**dict(row))


def users_create(
    conn: sqlite3.Connection,
    email: str,
    password_hash: str,
    role: str = "agent",
) -> int:
    cur = conn.execute(
        "INSERT INTO users(email, password_hash, role) VALUES (?,?,?)",
        (email, password_hash, role),
    )
    return cur.lastrowid


def users_get_by_email(conn: sqlite3.Connection, email: str) -> Optional[UserRow]:
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return _user_from_row(row) if row else None


def users_get(conn: sqlite3.Connection, user_id: int) -> Optional[UserRow]:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_from_row(row) if row else None


def users_list(conn: sqlite3.Connection) -> list[UserRow]:
    return [_user_from_row(r) for r in conn.execute("SELECT * FROM users ORDER BY id")]


def users_count_admins(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin'").fetchone()
    return int(row["c"])


def users_count_active_admins(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE role='admin' AND active=1"
    ).fetchone()
    return int(row["c"])


# ── watchlist ──────────────────────────────────────────────────


@dataclass
class WatchlistRow:
    id: int
    user_id: int
    name: str
    class_nice: Optional[int]
    notes: Optional[str]
    active: int
    created_at: str


def _watchlist_from_row(row: sqlite3.Row) -> WatchlistRow:
    return WatchlistRow(**dict(row))


def watchlist_add(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    class_nice: Optional[int] = None,
    notes: Optional[str] = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO watchlist(user_id, name, class_nice, notes) VALUES (?,?,?,?)",
        (user_id, name, class_nice, notes),
    )
    return cur.lastrowid


def watchlist_list_for_user(
    conn: sqlite3.Connection,
    user_id: int,
    only_active: bool = False,
) -> list[WatchlistRow]:
    sql = "SELECT * FROM watchlist WHERE user_id = ?"
    if only_active:
        sql += " AND active = 1"
    sql += " ORDER BY name"
    return [_watchlist_from_row(r) for r in conn.execute(sql, (user_id,))]


def watchlist_toggle(
    conn: sqlite3.Connection, watchlist_id: int, user_id: int, active: bool
) -> None:
    conn.execute(
        "UPDATE watchlist SET active = ? WHERE id = ? AND user_id = ?",
        (1 if active else 0, watchlist_id, user_id),
    )


# ── portfolio ──────────────────────────────────────────────────


@dataclass
class PortfolioRow:
    id: int
    user_id: int
    name: str
    expediente: Optional[str]
    class_nice: Optional[int]
    status: Optional[str]
    last_checked_at: Optional[str]
    notes: Optional[str]
    pais: str = "Venezuela"
    etiqueta: Optional[str] = None
    tipo_registro: Optional[str] = None
    bufete: Optional[str] = None
    solicitud: Optional[str] = None
    fecha_solicitud: Optional[str] = None
    registro: Optional[str] = None
    fecha_registro: Optional[str] = None
    fecha_vencimiento: Optional[str] = None
    titular: Optional[str] = None
    tramitante: Optional[str] = None
    empresa_licenciada: Optional[str] = None
    productos_servicios: Optional[str] = None
    comentarios: Optional[str] = None
    last_boletin_id: Optional[int] = None
    last_boletin_period: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


def _portfolio_from_row(row: sqlite3.Row) -> PortfolioRow:
    return PortfolioRow(**dict(row))


def _portfolio_ident_key(p: PortfolioRow) -> Optional[str]:
    """Clave de identidad para upsert: #REGISTRO (registrada) o #SOLICITUD.

    Una marca sin ni #registro ni #solicitud no se matchea contra el
    boletín (queda sin verificación) según la regla de identidad.
    """
    if p.registro:
        return f"registro:{p.registro.strip().upper()}"
    if p.solicitud:
        return f"solicitud:{p.solicitud.strip().upper()}"
    return None


def portfolio_add(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    expediente: Optional[str] = None,
    class_nice: Optional[int] = None,
    notes: Optional[str] = None,
    *,
    pais: Optional[str] = "Venezuela",
    etiqueta: Optional[str] = None,
    tipo_registro: Optional[str] = None,
    bufete: Optional[str] = None,
    solicitud: Optional[str] = None,
    fecha_solicitud: Optional[str] = None,
    registro: Optional[str] = None,
    fecha_registro: Optional[str] = None,
    fecha_vencimiento: Optional[str] = None,
    titular: Optional[str] = None,
    tramitante: Optional[str] = None,
    empresa_licenciada: Optional[str] = None,
    productos_servicios: Optional[str] = None,
    comentarios: Optional[str] = None,
    status: Optional[str] = None,
) -> int:
    if status is None:
        status = "Pendiente Resolución"
    cur = conn.execute(
        "INSERT INTO portfolio("
        " user_id, name, expediente, class_nice, notes,"
        " pais, etiqueta, tipo_registro, bufete,"
        " solicitud, fecha_solicitud, registro, fecha_registro,"
        " fecha_vencimiento, titular, tramitante, empresa_licenciada,"
        " productos_servicios, comentarios, status)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user_id, name, expediente, class_nice, notes,
            pais, etiqueta, tipo_registro, bufete,
            solicitud, fecha_solicitud, registro, fecha_registro,
            fecha_vencimiento, titular, tramitante, empresa_licenciada,
            productos_servicios, comentarios, status,
        ),
    )
    return cur.lastrowid


def portfolio_update(
    conn: sqlite3.Connection,
    portfolio_id: int,
    user_id: int,
    **fields: Any,
) -> None:
    """Actualiza una marca del portfolio (multi-tenant: exige user_id).

    Solo actualiza las columnas pasadas como kwargs. Marca ``updated_at``.
    """
    allowed = {
        "name", "expediente", "class_nice", "notes", "status",
        "pais", "etiqueta", "tipo_registro", "bufete",
        "solicitud", "fecha_solicitud", "registro", "fecha_registro",
        "fecha_vencimiento", "titular", "tramitante", "empresa_licenciada",
        "productos_servicios", "comentarios",
        "last_checked_at", "last_boletin_id", "last_boletin_period",
    }
    cols = [k for k in fields if k in allowed]
    if not cols:
        return
    set_clause = ", ".join(f"{c} = ?" for c in cols)
    conn.execute(
        f"UPDATE portfolio SET {set_clause}, updated_at = datetime('now')"
        " WHERE id = ? AND user_id = ?",
        (*[fields[c] for c in cols], portfolio_id, user_id),
    )


def portfolio_get(
    conn: sqlite3.Connection, portfolio_id: int, user_id: Optional[int] = None
) -> Optional[PortfolioRow]:
    if user_id is None:
        row = conn.execute(
            "SELECT * FROM portfolio WHERE id = ?", (portfolio_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM portfolio WHERE id = ? AND user_id = ?",
            (portfolio_id, user_id),
        ).fetchone()
    return _portfolio_from_row(row) if row else None


def portfolio_list_for_user(
    conn: sqlite3.Connection, user_id: int
) -> list[PortfolioRow]:
    return [
        _portfolio_from_row(r)
        for r in conn.execute(
            "SELECT * FROM portfolio WHERE user_id = ? ORDER BY name", (user_id,)
        )
    ]


def portfolio_find_by_identity(
    conn: sqlite3.Connection, user_id: int, *, registro: Optional[str] = None,
    solicitud: Optional[str] = None, expediente: Optional[str] = None,
) -> Optional[PortfolioRow]:
    """Devuelve la marca del usuario identificada por #REGISTRO / #SOLICITUD.

    Prioridad de identidad (regla del módulo portfolio):
    registrada → #REGISTRO; por registrar → #SOLICITUD; fallback
    retrocompatible → expediente.
    """
    for value, col in ((registro, "registro"), (solicitud, "solicitud"), (expediente, "expediente")):
        if not value or not str(value).strip():
            continue
        row = conn.execute(
            f"SELECT * FROM portfolio WHERE user_id = ? AND TRIM(UPPER({col})) = ?",
            (user_id, str(value).strip().upper()),
        ).fetchone()
        if row:
            return _portfolio_from_row(row)
    return None


def portfolio_update_status(
    conn: sqlite3.Connection,
    portfolio_id: int,
    status: str,
    user_id: int,
    *,
    boletin_id: Optional[int] = None,
    boletin_period: Optional[str] = None,
) -> None:
    conn.execute(
        "UPDATE portfolio SET status = ?, last_checked_at = datetime('now'),"
        " last_boletin_id = COALESCE(?, last_boletin_id),"
        " last_boletin_period = COALESCE(?, last_boletin_period),"
        " updated_at = datetime('now')"
        " WHERE id = ? AND user_id = ?",
        (status, boletin_id, boletin_period, portfolio_id, user_id),
    )


# ── portfolio_history ──────────────────────────────────────────


@dataclass
class PortfolioHistoryRow:
    id: int
    portfolio_id: int
    user_id: int
    boletin_id: Optional[int]
    boletin_period: Optional[str]
    boletin_number: Optional[int]
    estado: Optional[str]
    snapshot_json: str
    created_at: str

    @property
    def snapshot(self) -> dict[str, Any]:
        try:
            return json.loads(self.snapshot_json or "{}")
        except (ValueError, TypeError):
            return {}


def _history_from_row(row: sqlite3.Row) -> PortfolioHistoryRow:
    return PortfolioHistoryRow(**dict(row))


def portfolio_history_add(
    conn: sqlite3.Connection,
    *,
    portfolio_id: int,
    user_id: int,
    boletin_id: Optional[int],
    boletin_period: Optional[str],
    boletin_number: Optional[int],
    estado: Optional[str],
    snapshot: dict[str, Any],
) -> int:
    cur = conn.execute(
        "INSERT OR IGNORE INTO portfolio_history("
        " portfolio_id, user_id, boletin_id, boletin_period,"
        " boletin_number, estado, snapshot_json)"
        " VALUES (?,?,?,?,?,?,?)",
        (
            portfolio_id, user_id, boletin_id, boletin_period,
            boletin_number, estado,
            json.dumps(snapshot, ensure_ascii=False, default=str),
        ),
    )
    return cur.lastrowid


def portfolio_history_list(
    conn: sqlite3.Connection, portfolio_id: int, user_id: int
) -> list[PortfolioHistoryRow]:
    return [
        _history_from_row(r)
        for r in conn.execute(
            "SELECT * FROM portfolio_history WHERE portfolio_id = ? AND user_id = ?"
            " ORDER BY id DESC",
            (portfolio_id, user_id),
        )
    ]


# ── boletines ───────────────────────────────────────────────────


@dataclass
class BoletinRow:
    id: int
    uploaded_by: int
    filename: str
    file_path: str
    file_sha256: str
    bulletin_number: Optional[int]
    period: Optional[str]
    pages: Optional[int]
    status: str
    extraction_json: Optional[str]
    needs_hermes_review: int
    hermes_processed_at: Optional[str]
    hermes_error: Optional[str]
    error: Optional[str]
    uploaded_at: str
    processed_at: Optional[str]
    entries_matcheables: int = 0
    entries_hermes_pending: int = 0
    entries_figura: int = 0
    entries_lema: int = 0
    progress_step: Optional[str] = None
    progress_current_page: Optional[int] = None
    progress_total_pages: Optional[int] = None


def _boletin_from_row(row: sqlite3.Row) -> BoletinRow:
    return BoletinRow(**dict(row))


def boletines_create(
    conn: sqlite3.Connection,
    uploaded_by: int,
    filename: str,
    file_path: str,
    file_sha256: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO boletines(uploaded_by, filename, file_path, file_sha256, status)"
        " VALUES (?,?,?,?,'extracting')",
        (uploaded_by, filename, file_path, file_sha256),
    )
    return cur.lastrowid


def boletines_mark_extracted(
    conn: sqlite3.Connection,
    boletin_id: int,
    pages: int,
    extraction_payload: dict[str, Any],
    bulletin_number: Optional[int],
    period: Optional[str],
    needs_hermes_review: bool,
    entries_matcheables: int = 0,
    entries_hermes_pending: int = 0,
    entries_figura: int = 0,
    entries_lema: int = 0,
) -> None:
    conn.execute(
        "UPDATE boletines SET"
        " status = 'extracted',"
        " pages = ?,"
        " extraction_json = ?,"
        " bulletin_number = ?,"
        " period = ?,"
        " needs_hermes_review = ?,"
        " entries_matcheables = ?,"
        " entries_hermes_pending = ?,"
        " entries_figura = ?,"
        " entries_lema = ?,"
        " processed_at = datetime('now')"
        " WHERE id = ?",
        (
            pages,
            json.dumps(extraction_payload, ensure_ascii=False),
            bulletin_number,
            period,
            1 if needs_hermes_review else 0,
            entries_matcheables,
            entries_hermes_pending,
            entries_figura,
            entries_lema,
            boletin_id,
        ),
    )


def boletines_mark_failed(
    conn: sqlite3.Connection, boletin_id: int, error: str
) -> None:
    conn.execute(
        "UPDATE boletines SET status='failed', error=?, progress_step='failed' WHERE id = ?",
        (error, boletin_id),
    )


def boletines_update_progress(
    conn: sqlite3.Connection,
    boletin_id: int,
    *,
    step: Optional[str] = None,
    current_page: Optional[int] = None,
    total_pages: Optional[int] = None,
) -> None:
    """Actualiza el progreso visible del boletín (status='extracting').

    Los parámetros ``None`` no se tocan; pasar un valor lo actualiza.
    """
    sets: list[str] = []
    params: list = []
    if step is not None:
        sets.append("progress_step = ?")
        params.append(step)
    if current_page is not None:
        sets.append("progress_current_page = ?")
        params.append(current_page)
    if total_pages is not None:
        sets.append("progress_total_pages = ?")
        params.append(total_pages)
    if not sets:
        return
    params.append(boletin_id)
    conn.execute(
        f"UPDATE boletines SET {', '.join(sets)} WHERE id = ?",
        params,
    )


def boletines_get(conn: sqlite3.Connection, boletin_id: int) -> Optional[BoletinRow]:
    row = conn.execute("SELECT * FROM boletines WHERE id = ?", (boletin_id,)).fetchone()
    return _boletin_from_row(row) if row else None


def boletines_count_with_sha(conn: sqlite3.Connection, file_sha256: str) -> int:
    """Cuenta cuántos boletines comparten el mismo `file_sha256`.

    Se usa antes de borrar el PDF en disco: si queda al menos uno, no
    se elimina el archivo (otro boletín lo sigue referenciando).
    """
    row = conn.execute(
        "SELECT COUNT(*) FROM boletines WHERE file_sha256 = ?",
        (file_sha256,),
    ).fetchone()
    return int(row[0]) if row else 0


def boletines_delete(conn: sqlite3.Connection, boletin_id: int) -> None:
    """Elimina la fila del boletín y sus dependencias.

    Las `detections` caen por CASCADE del FK. `scans_log` también
    referencia `boletines.id` pero sin CASCADE (esquema heredado), así
    que se borra explícitamente antes para no violar FK en bases
    creadas con la versión antigua del esquema.
    """
    conn.execute("DELETE FROM scans_log WHERE boletin_id = ?", (boletin_id,))
    conn.execute("DELETE FROM boletines WHERE id = ?", (boletin_id,))


def boletines_list_pending_hermes(
    conn: sqlite3.Connection, limit: int = 50
) -> list[BoletinRow]:
    return [
        _boletin_from_row(r)
        for r in conn.execute(
            "SELECT * FROM boletines"
            " WHERE needs_hermes_review = 1"
            "   AND hermes_processed_at IS NULL"
            "   AND status IN ('extracted','hermes_pending')"
            " ORDER BY id LIMIT ?",
            (limit,),
        )
    ]


def boletines_list_recent(
    conn: sqlite3.Connection, user_id: Optional[int] = None, limit: int = 50
) -> list[BoletinRow]:
    if user_id is None:
        rows = conn.execute(
            "SELECT * FROM boletines ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM boletines WHERE uploaded_by = ?"
            " ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [_boletin_from_row(r) for r in rows]


# ── detections ─────────────────────────────────────────────────


@dataclass
class DetectionRow:
    id: int
    boletin_id: int
    user_id: int
    watchlist_id: Optional[int]
    portfolio_id: Optional[int]
    expediente: Optional[str]
    mark_name: str
    titular: Optional[str]
    class_nice: Optional[int]
    page: Optional[int]
    similarity: float
    match_kind: str
    source: str
    confidence: str
    raw_excerpt: Optional[str]
    detected_at: str
    notified_email: int
    notified_at: Optional[str]
    pais: Optional[str] = None
    fecha_inscripcion: Optional[str] = None
    fuente_parsing: Optional[str] = None
    es_figura: int = 0
    es_lema: int = 0
    needs_hermes_reverify: int = 0


def _detection_from_row(row: sqlite3.Row) -> DetectionRow:
    return DetectionRow(**dict(row))


def detections_add(
    conn: sqlite3.Connection,
    *,
    boletin_id: int,
    user_id: int,
    mark_name: str,
    similarity: float,
    match_kind: str,
    source: str,
    confidence: str,
    watchlist_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
    expediente: Optional[str] = None,
    titular: Optional[str] = None,
    class_nice: Optional[int] = None,
    page: Optional[int] = None,
    raw_excerpt: Optional[str] = None,
    pais: Optional[str] = None,
    fecha_inscripcion: Optional[str] = None,
    fuente_parsing: Optional[str] = None,
    es_figura: int = 0,
    es_lema: int = 0,
) -> int:
    cur = conn.execute(
        "INSERT OR IGNORE INTO detections("
        " boletin_id, user_id, watchlist_id, portfolio_id,"
        " expediente, mark_name, titular, class_nice, page,"
        " similarity, match_kind, source, confidence, raw_excerpt,"
        " pais, fecha_inscripcion, fuente_parsing, es_figura, es_lema)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            boletin_id,
            user_id,
            watchlist_id,
            portfolio_id,
            expediente,
            mark_name,
            titular,
            class_nice,
            page,
            similarity,
            match_kind,
            source,
            confidence,
            raw_excerpt,
            pais,
            fecha_inscripcion,
            fuente_parsing,
            es_figura,
            es_lema,
        ),
    )
    return cur.lastrowid


def detections_list_for_user(
    conn: sqlite3.Connection,
    user_id: int,
    limit: int = 100,
    boletin_id: Optional[int] = None,
) -> list[DetectionRow]:
    if boletin_id is not None:
        rows = conn.execute(
            "SELECT * FROM detections WHERE user_id = ? AND boletin_id = ?"
            " ORDER BY similarity DESC, id DESC LIMIT ?",
            (user_id, boletin_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM detections WHERE user_id = ?"
            " ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [_detection_from_row(r) for r in rows]


def detections_pending_notification(
    conn: sqlite3.Connection, user_id: int, limit: int = 100
) -> list[DetectionRow]:
    rows = conn.execute(
        "SELECT * FROM detections WHERE user_id = ? AND notified_email = 0"
        " ORDER BY id ASC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [_detection_from_row(r) for r in rows]


def detections_mark_notified(
    conn: sqlite3.Connection, detection_ids: Iterable[int]
) -> None:
    ids = list(detection_ids)
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE detections SET notified_email = 1, notified_at = datetime('now')"
        f" WHERE id IN ({placeholders})",
        ids,
    )


# ── scans_log ──────────────────────────────────────────────────


def scans_log_record(
    conn: sqlite3.Connection,
    *,
    kind: str,
    status: str,
    user_id: Optional[int] = None,
    boletin_id: Optional[int] = None,
    summary: Optional[str] = None,
    detail: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO scans_log(user_id, kind, boletin_id, summary, status,"
        " detail, duration_ms) VALUES (?,?,?,?,?,?,?)",
        (user_id, kind, boletin_id, summary, status, detail, duration_ms),
    )
    return cur.lastrowid


# ── stats helpers ──────────────────────────────────────────────


@dataclass
class UserStats:
    watchlist_count: int
    portfolio_count: int
    boletines_count: int
    detections_count: int
    last_boletin_at: Optional[str]


def stats_for_user(conn: sqlite3.Connection, user_id: int) -> UserStats:
    def _scalar(sql: str, params: tuple = ()) -> int:
        row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    return UserStats(
        watchlist_count=_scalar(
            "SELECT COUNT(*) FROM watchlist WHERE user_id=?", (user_id,)
        ),
        portfolio_count=_scalar(
            "SELECT COUNT(*) FROM portfolio WHERE user_id=?", (user_id,)
        ),
        boletines_count=_scalar(
            "SELECT COUNT(*) FROM boletines WHERE uploaded_by=?", (user_id,)
        ),
        detections_count=_scalar(
            "SELECT COUNT(*) FROM detections WHERE user_id=?", (user_id,)
        ),
        last_boletin_at=conn.execute(
            "SELECT MAX(uploaded_at) FROM boletines WHERE uploaded_by=?",
            (user_id,),
        ).fetchone()[0],
    )

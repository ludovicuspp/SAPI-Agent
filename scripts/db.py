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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','agent','propietario','empresa')),
    nombre TEXT NOT NULL DEFAULT '',
    acciones TEXT NOT NULL DEFAULT '[]',
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
    productos_servicios TEXT,
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
    uploaded_by INTEGER REFERENCES users(id),
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
    progress_total_pages INTEGER,
    progress_updated_at TEXT,
    checkpoint_json TEXT,
    processing_batch INTEGER,
    hermes_progress_step TEXT,
    hermes_progress_current_page INTEGER,
    hermes_progress_total_pages INTEGER,
    hermes_progress_updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_boletines_status ON boletines(status);
CREATE INDEX IF NOT EXISTS idx_boletines_needs_hermes
    ON boletines(needs_hermes_review, hermes_processed_at);

CREATE TABLE IF NOT EXISTS boletin_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boletin_id INTEGER NOT NULL REFERENCES boletines(id) ON DELETE CASCADE,
    expediente TEXT NOT NULL,
    marca TEXT,
    class_nice INTEGER,
    clase_especial TEXT,
    titular TEXT,
    pais TEXT,
    fecha_inscripcion TEXT,
    estatus TEXT,
    page INTEGER,
    is_matcheable INTEGER NOT NULL DEFAULT 0,
    is_figura INTEGER NOT NULL DEFAULT 0,
    is_lema INTEGER NOT NULL DEFAULT 0,
    productos_servicios TEXT,
    fuente_parsing TEXT,
    source TEXT,
    excerpt TEXT,
    entry_json TEXT,
    UNIQUE(boletin_id, expediente)
);
CREATE INDEX IF NOT EXISTS idx_be_boletin ON boletin_entries(boletin_id);
CREATE INDEX IF NOT EXISTS idx_be_marca ON boletin_entries(marca);
CREATE INDEX IF NOT EXISTS idx_be_clase ON boletin_entries(class_nice);

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
    matched_with TEXT,
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
        ("boletines", "progress_updated_at", "TEXT"),
        ("boletines", "checkpoint_json", "TEXT"),
        ("boletines", "processing_batch", "INTEGER"),
        ("boletines", "hermes_progress_step", "TEXT"),
        ("boletines", "hermes_progress_current_page", "INTEGER"),
        ("boletines", "hermes_progress_total_pages", "INTEGER"),
        ("boletines", "hermes_progress_updated_at", "TEXT"),
        ("detections", "pais", "TEXT"),
        ("detections", "fecha_inscripcion", "TEXT"),
        ("detections", "fuente_parsing", "TEXT"),
        ("detections", "es_figura", "INTEGER NOT NULL DEFAULT 0"),
        ("detections", "es_lema", "INTEGER NOT NULL DEFAULT 0"),
        ("detections", "needs_hermes_reverify", "INTEGER NOT NULL DEFAULT 0"),
        ("detections", "matched_with", "TEXT"),
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
        ("watchlist", "productos_servicios", "TEXT"),
        ("portfolio", "last_boletin_id", "INTEGER"),
        ("portfolio", "last_boletin_period", "TEXT"),
        ("portfolio", "updated_at", "TEXT NOT NULL DEFAULT ''"),
    ]
    for table, column, typedef in migrations:
        try:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {typedef}"
            )
        except sqlite3.OperationalError:
            # La columna ya existe; ignorar.
            pass
    _migrate_users_drop_active(conn)
    _migrate_boletines_uploaded_by_nullable(conn)
    _migrate_users_role_check(conn)
    _backfill_detections_matched_with(conn)
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


def _backfill_detections_matched_with(conn: sqlite3.Connection) -> None:
    """Rellena ``matched_with`` para detecciones existentes que aún no
    lo tienen, tomando el nombre de la watchlist o portfolio asociado.

    Idempotente: solo actualiza las filas con ``matched_with IS NULL``.
    """
    try:
        conn.execute(
            """
            UPDATE detections
            SET matched_with = COALESCE(
                (SELECT name FROM watchlist WHERE watchlist.id = detections.watchlist_id),
                (SELECT name FROM portfolio WHERE portfolio.id = detections.portfolio_id),
                NULL
            )
            WHERE matched_with IS NULL
              AND (watchlist_id IS NOT NULL OR portfolio_id IS NOT NULL)
            """
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass


def _migrate_users_drop_active(conn: sqlite3.Connection) -> None:
    """Elimina la columna ``active`` de ``users`` si existe.

    Los usuarios ahora se borran (DELETE real) en vez de desactivarse.
    ``ALTER TABLE ... DROP COLUMN`` requiere SQLite 3.35+ (Python 3.12+).
    Idempotente: si la columna no existe, SQLite lanza OperationalError
    que se ignora.
    """
    try:
        conn.execute("ALTER TABLE users DROP COLUMN active")
    except sqlite3.OperationalError:
        pass


def _migrate_boletines_uploaded_by_nullable(conn: sqlite3.Connection) -> None:
    """Hace ``boletines.uploaded_by`` NULL-able.

    Necesario para poder borrar un usuario y conservar los boletines
    que subió (``boletines`` no se puede CASCADE-borrar porque
    ``detections.boletin_id`` los referencia).

    Reconstruye la tabla con el patrón 12-step bajo
    ``PRAGMA legacy_alter_table=ON`` y ``foreign_keys=OFF`` para que
    ``ALTER TABLE ... RENAME`` no reescriba los ``REFERENCES`` de las
    tablas hijas (detections, portfolio, portfolio_history, scans_log).
    Idempotente: si la columna ya admite NULL, no hace nada.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='boletines'"
    ).fetchone()
    if row is None:
        return
    create_sql = row[0]
    if "uploaded_by INTEGER REFERENCES" in create_sql or "uploaded_by INTEGER NULL" in create_sql:
        # Variantes "REFERENCES" sin NOT NULL; ya es nullable.
        if "uploaded_by INTEGER NOT NULL" not in create_sql:
            return

    # Captura índices de boletines para recrearlos tras el rebuild.
    indexes = [
        r[0]
        for r in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name='boletines' AND sql IS NOT NULL"
        ).fetchall()
    ]

    new_create = (
        "CREATE TABLE boletines (\n"
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "    uploaded_by INTEGER REFERENCES users(id),\n"
        "    filename TEXT NOT NULL,\n"
        "    file_path TEXT NOT NULL,\n"
        "    file_sha256 TEXT NOT NULL,\n"
        "    bulletin_number INTEGER,\n"
        "    period TEXT,\n"
        "    pages INTEGER,\n"
        "    status TEXT NOT NULL DEFAULT 'pending'\n"
        "        CHECK (status IN ('pending','extracting','extracted',\n"
        "                          'hermes_pending','hermes_done','failed')),\n"
        "    extraction_json TEXT,\n"
        "    needs_hermes_review INTEGER NOT NULL DEFAULT 0,\n"
        "    hermes_processed_at TEXT,\n"
        "    hermes_error TEXT,\n"
        "    error TEXT,\n"
        "    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),\n"
        "    processed_at TEXT,\n"
        "    entries_matcheables INTEGER NOT NULL DEFAULT 0,\n"
        "    entries_hermes_pending INTEGER NOT NULL DEFAULT 0,\n"
        "    entries_figura INTEGER NOT NULL DEFAULT 0,\n"
        "    entries_lema INTEGER NOT NULL DEFAULT 0,\n"
        "    progress_step TEXT,\n"
        "    progress_current_page INTEGER,\n"
        "    progress_total_pages INTEGER,\n"
        "    progress_updated_at TEXT,\n"
        "    checkpoint_json TEXT,\n"
        "    processing_batch INTEGER,\n"
        "    hermes_progress_step TEXT,\n"
        "    hermes_progress_current_page INTEGER,\n"
        "    hermes_progress_total_pages INTEGER,\n"
        "    hermes_progress_updated_at TEXT\n"
        ");"
    )

    conn.execute("PRAGMA legacy_alter_table = ON")
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("ALTER TABLE boletines RENAME TO boletines_legacy")
        conn.execute(new_create)
        new_cols = {
            c[1] for c in conn.execute("PRAGMA table_info(boletines)")
        }
        old_cols = [
            c[1]
            for c in conn.execute("PRAGMA table_info(boletines_legacy)")
            if c[1] in new_cols
        ]
        collist = ", ".join(old_cols)
        conn.execute(
            f"INSERT INTO boletines ({collist}) "
            f"SELECT {collist} FROM boletines_legacy"
        )
        conn.execute("DROP TABLE boletines_legacy")
        for idx_sql in indexes:
            conn.execute(idx_sql)
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA legacy_alter_table = OFF")


def _migrate_users_role_check(conn: sqlite3.Connection) -> None:
    """Amplía el CHECK de roles de la tabla users en BD existentes.

    SQLite no permite ``ALTER CONSTRAINT``, así que se reconstruye la
    tabla (patrón 12-step). La reconstrucción se hace con
    ``PRAGMA legacy_alter_table=ON`` (y ``foreign_keys=OFF``): con el
    comportamiento moderno, ``ALTER TABLE users RENAME TO users_legacy``
    reescribe los ``REFERENCES`` de las tablas hijas hacia
    ``users_legacy``, y el ``DROP TABLE users_legacy`` posterior falla
    por dependencia (dejando la BD a medias).

    También recupera un 12-step fallido de una versión anterior: si
    queda una tabla ``users_legacy``, se fusionan las filas que falten
    en ``users`` y se reconstruyen las tablas hijas cuyo ``REFERENCES``
    haya quedado apuntando a ``users_legacy``. Idempotente.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    create_sql = row[0] if row else None
    legacy_exists = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users_legacy'"
        ).fetchone()
        is not None
    )
    already_new = create_sql is not None and "propietario" in create_sql

    # Estado normal (ya migrado y sin resto): no hay nada que hacer.
    if already_new and not legacy_exists:
        return

    conn.execute("PRAGMA legacy_alter_table = ON")
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        # 1) Repara tablas hijas cuyo REFERENCES quedó apuntando a
        #    users_legacy (recuperación de un 12-step fallido).
        for tbl, sql in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'"
        ).fetchall():
            if not sql or '"users_legacy"(id)' not in sql:
                continue
            tmp = f'"{tbl}_repair"'
            conn.execute(f'ALTER TABLE "{tbl}" RENAME TO {tmp}')
            conn.execute(sql.replace('"users_legacy"(id)', '"users"(id)'))
            cols = ", ".join(
                c[1] for c in conn.execute(f"PRAGMA table_info({tmp})")
            )
            conn.execute(
                f'INSERT INTO "{tbl}" ({cols}) SELECT {cols} FROM {tmp}'
            )
            conn.execute(f"DROP TABLE {tmp}")

        # 2) Reconstruye users con el CHECK ampliado si aún es vieja.
        if not already_new:
            if create_sql is not None:
                conn.execute("ALTER TABLE users RENAME TO users_legacy")
            conn.execute(
                "CREATE TABLE users (\n"
                "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                "    email TEXT NOT NULL UNIQUE,\n"
                "    password_hash TEXT NOT NULL,\n"
                "    role TEXT NOT NULL CHECK (role IN ('admin','agent','propietario','empresa')),\n"
                "    nombre TEXT NOT NULL DEFAULT '',\n"
                "    acciones TEXT NOT NULL DEFAULT '[]',\n"
                "    created_at TEXT NOT NULL DEFAULT (datetime('now')),\n"
                "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))\n"
                ");"
            )

        # 3) Fusiona lo que falte desde users_legacy y lo elimina.
        #    Se re-consulta el master: en el path "fresco" acabamos de
        #    crear users_legacy con el RENAME del paso 2.
        legacy_now = (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='users_legacy'"
            ).fetchone()
            is not None
        )
        if legacy_now:
            users_cols = {c[1] for c in conn.execute("PRAGMA table_info(users)")}
            cols = ", ".join(
                c[1]
                for c in conn.execute("PRAGMA table_info(users_legacy)")
                if c[1] in users_cols
            )
            conn.execute(
                f"INSERT INTO users ({cols}) "
                f"SELECT {cols} FROM users_legacy "
                f"WHERE id NOT IN (SELECT id FROM users)"
            )
            conn.execute("DROP TABLE users_legacy")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA legacy_alter_table = OFF")

    issues = conn.execute("PRAGMA foreign_key_check").fetchall()
    if issues:
        import warnings
        warnings.warn(
            f"foreign_key_check: {len(issues)} violación(es) pre-existente(s) "
            "que no afectan esta migración. Ejecutar PRAGMA foreign_key_check "
            "para detalles."
        )


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
    nombre: str
    acciones: str
    created_at: str
    updated_at: str

    @property
    def acciones_list(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.acciones or "[]")
        except (ValueError, TypeError):
            return []


def _user_from_row(row: sqlite3.Row) -> UserRow:
    return UserRow(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=row["role"],
        nombre=row["nombre"] if "nombre" in row.keys() else "",
        acciones=row["acciones"] if "acciones" in row.keys() else "[]",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def users_create(
    conn: sqlite3.Connection,
    email: str,
    password_hash: str,
    role: str = "agent",
    nombre: str = "",
) -> int:
    cur = conn.execute(
        "INSERT INTO users(email, password_hash, role, nombre) VALUES (?,?,?,?)",
        (email, password_hash, role, nombre or ""),
    )
    return cur.lastrowid


def user_log_action(
    conn: sqlite3.Connection, user_id: int, accion: str, *, commit: bool = True
) -> None:
    """Registra una acción en el historial JSON del usuario.

    Cada entrada es ``{"accion": ..., "timestamp": ...}``. El historial
    se mantiene en orden (más reciente al final).
    """
    row = conn.execute("SELECT acciones FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return
    try:
        current = json.loads(row["acciones"] or "[]")
        if not isinstance(current, list):
            current = []
    except (ValueError, TypeError):
        current = []
    current.append({
        "accion": accion,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    conn.execute(
        "UPDATE users SET acciones = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(current, ensure_ascii=False), user_id),
    )
    if commit:
        conn.commit()


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


def users_delete(conn: sqlite3.Connection, user_id: int) -> None:
    """Borra un usuario definitivamente.

    - ``watchlist`` / ``portfolio`` / ``detections`` / ``portfolio_history``
      se borran en cascada vía FK (datos privados del usuario).
    - ``boletines`` y ``scans_log`` aportan contexto al sistema y no son
      propiedad del usuario: se desliga su referencia (``uploaded_by`` /
      ``user_id`` → NULL) y se conservan.
    """
    conn.execute(
        "UPDATE boletines SET uploaded_by = NULL WHERE uploaded_by = ?",
        (user_id,),
    )
    conn.execute(
        "UPDATE scans_log SET user_id = NULL WHERE user_id = ?",
        (user_id,),
    )
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()


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
    productos_servicios: Optional[str] = None


def _watchlist_from_row(row: sqlite3.Row) -> WatchlistRow:
    return WatchlistRow(**dict(row))


def watchlist_add(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    class_nice: Optional[int] = None,
    notes: Optional[str] = None,
    *,
    productos_servicios: Optional[str] = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO watchlist(user_id, name, class_nice, notes, productos_servicios)"
        " VALUES (?,?,?,?,?)",
        (user_id, name, class_nice, notes, productos_servicios),
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
    uploaded_by: Optional[int]
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
    progress_updated_at: Optional[str] = None
    checkpoint_json: Optional[str] = None
    processing_batch: Optional[int] = None
    hermes_progress_step: Optional[str] = None
    hermes_progress_current_page: Optional[int] = None
    hermes_progress_total_pages: Optional[int] = None
    hermes_progress_updated_at: Optional[str] = None


def _boletin_from_row(row: sqlite3.Row) -> BoletinRow:
    return BoletinRow(**dict(row))


def boletines_create(
    conn: sqlite3.Connection,
    uploaded_by: Optional[int],
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
        " checkpoint_json = NULL,"
        " processing_batch = NULL,"
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
    Siempre escribe ``progress_updated_at = datetime('now')`` para que
    el sweep de huérfanos tenga una señal temporal fiable.
    """
    sets: list[str] = ["progress_updated_at = datetime('now')"]
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
    params.append(boletin_id)
    conn.execute(
        f"UPDATE boletines SET {', '.join(sets)} WHERE id = ?",
        params,
    )


def boletines_update_hermes_progress(
    conn: sqlite3.Connection,
    boletin_id: int,
    *,
    step: Optional[str] = None,
    current_page: Optional[int] = None,
    total_pages: Optional[int] = None,
) -> None:
    """Actualiza el progreso de análisis de Hermes Vision (página a página).

    Solo válido cuando el boletín está en ``extracted`` con
    ``needs_hermes_review=1`` y aún sin ``hermes_processed_at``.
    Siempre escribe ``hermes_progress_updated_at`` como señal temporal.
    """
    sets: list[str] = ["hermes_progress_updated_at = datetime('now')"]
    params: list = []
    if step is not None:
        sets.append("hermes_progress_step = ?")
        params.append(step)
    if current_page is not None:
        sets.append("hermes_progress_current_page = ?")
        params.append(current_page)
    if total_pages is not None:
        sets.append("hermes_progress_total_pages = ?")
        params.append(total_pages)
    params.append(boletin_id)
    conn.execute(
        f"UPDATE boletines SET {', '.join(sets)} WHERE id = ?",
        params,
    )


def boletines_mark_hermes_progress_done(
    conn: sqlite3.Connection, boletin_id: int
) -> None:
    """Marca el progreso de Hermes como terminado y fija hermes_processed_at."""
    conn.execute(
        "UPDATE boletines SET"
        " hermes_progress_step = 'done',"
        " hermes_progress_current_page = COALESCE(hermes_progress_total_pages, hermes_progress_current_page),"
        " hermes_progress_updated_at = datetime('now'),"
        " hermes_processed_at = datetime('now')"
        " WHERE id = ?",
        (boletin_id,),
    )


def boletines_save_checkpoint(
    conn: sqlite3.Connection,
    boletin_id: int,
    *,
    batch: int,
    checkpoints: dict[str, Any],
) -> None:
    """Persiste el checkpoint de extracción por lotes del boletín.

    ``batch`` es el número de lote completado. ``checkpoints`` es un
    dict JSON-serializable con flags agregados (has_images, low_conf,
    cid_encoding, last_page, counts). Permite reanudar una extracción
    interrumpida (OOM/SIGKILL) sin volver a procesar los lotes previos.
    """
    conn.execute(
        "UPDATE boletines SET checkpoint_json = ?, processing_batch = ? WHERE id = ?",
        (json.dumps(checkpoints, ensure_ascii=False, default=str), batch, boletin_id),
    )


def boletines_get_checkpoint(
    conn: sqlite3.Connection, boletin_id: int
) -> tuple[Optional[int], dict[str, Any]]:
    """Devuelve ``(batch, checkpoints)`` actuales del boletín.

    Si el boletín no tiene checkpoint, ``batch`` es ``None`` y
    ``checkpoints`` es ``{}``.
    """
    row = conn.execute(
        "SELECT checkpoint_json, processing_batch FROM boletines WHERE id = ?",
        (boletin_id,),
    ).fetchone()
    if not row:
        return None, {}
    try:
        ck = json.loads(row["checkpoint_json"]) if row["checkpoint_json"] else {}
    except (ValueError, TypeError):
        ck = {}
    if not isinstance(ck, dict):
        ck = {}
    return row["processing_batch"], ck


def boletines_mark_stale_extracting_as_failed(
    conn: sqlite3.Connection,
    *,
    threshold_minutes: int = 10,
) -> list[int]:
    """Marca como ``failed`` los boletines en ``extracting`` con tareas
    huérfanas.

    Detecta tres casos:
      1. ``progress_step IS NULL`` y ``uploaded_at > N min``: tarea que
         murió antes de empezar a reportar progreso (crash de import,
         OOM al cargar el PDF, etc.).
      2. ``progress_step`` no terminal y ``progress_updated_at > N min``:
         tarea que reportó progreso pero quedó atascada a mitad
         (kill -9 del servicio, SIGKILL del proceso, etc.).
      3. ``progress_updated_at IS NULL`` y ``progress_step`` no terminal
         y ``uploaded_at > N min``: boletines subidos antes de que se
         añadiera la columna ``progress_updated_at`` (``90e843d``); su
         ``progress_step`` quedó con valor pero sin timestamp fiable.

    Esta función la invoca ``_process_boletin_task`` al arrancar (antes
    de empezar la suya) para limpiar el estado de runs anteriores que
    murieron silenciosamente.

    Devuelve la lista de boletines marcados.
    """
    rows = conn.execute(
        "SELECT id, filename FROM boletines "
        " WHERE status = 'extracting'"
        "   AND ("
        "        (progress_step IS NULL"
        "           AND datetime(uploaded_at) < datetime('now', ?))"
        "        OR (progress_updated_at IS NOT NULL"
        "           AND progress_step NOT IN ('done', 'failed')"
        "           AND datetime(progress_updated_at) < datetime('now', ?))"
        "        OR (progress_updated_at IS NULL"
        "           AND progress_step IS NOT NULL"
        "           AND progress_step NOT IN ('done', 'failed')"
        "           AND datetime(uploaded_at) < datetime('now', ?))"
        "   )",
        (
            f"-{threshold_minutes} minutes",
            f"-{threshold_minutes} minutes",
            f"-{threshold_minutes} minutes",
        ),
    ).fetchall()
    if not rows:
        return []
    ids = [r[0] for r in rows]
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE boletines SET status='failed', "
        f"error='Tarea de extracción no respondía (huérfana tras >{threshold_minutes} min)', "
        f"progress_step='failed' WHERE id IN ({placeholders})",
        ids,
    )
    for r in rows:
        scans_log_record(
            conn,
            kind="extract",
            status="error",
            boletin_id=r[0],
            detail=(
                f"Tarea huérfana (filename={r[1]}); marcada failed "
                f"automáticamente tras >{threshold_minutes} min sin progreso."
            ),
        )
    return ids


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


@dataclass
class BoletinEntryRow:
    """Una marca extraída de un boletín (capa fuente neutral).

    A diferencia de ``detections`` (multi-tenant y match-dependiente), aquí
    se persisten TODAS las marcas del boletín para poder consultarlas en el
    futuro, sin importar si matchean con una watchlist/portfolio.
    """
    id: int
    boletin_id: int
    expediente: str
    marca: Optional[str] = None
    class_nice: Optional[int] = None
    clase_especial: Optional[str] = None
    titular: Optional[str] = None
    pais: Optional[str] = None
    fecha_inscripcion: Optional[str] = None
    estatus: Optional[str] = None
    page: Optional[int] = None
    is_matcheable: int = 0
    is_figura: int = 0
    is_lema: int = 0
    productos_servicios: Optional[str] = None
    fuente_parsing: Optional[str] = None
    source: Optional[str] = None
    excerpt: Optional[str] = None
    entry_json: Optional[str] = None


def _entry_from_row(
    conn: sqlite3.Connection, r: sqlite3.Row
) -> BoletinEntryRow:
    return BoletinEntryRow(**dict(r))


def _entry_insert_values(
    boletin_id: int, e: Any
) -> dict[str, Any]:
    """Normaliza una entrada (parser ``MarcaEntry`` o shape Hermes) a columnas."""
    _fecha = getattr(e, "fecha_inscripcion", None)
    if hasattr(_fecha, "isoformat"):
        _fecha = _fecha.isoformat()
    return {
        "boletin_id": boletin_id,
        "expediente": getattr(e, "expediente", None),
        "marca": getattr(e, "marca", None),
        "class_nice": getattr(e, "class_nice", None)
        or getattr(e, "clase_niza", None) or getattr(e, "clase", None),
        "clase_especial": getattr(e, "clase_especial", None),
        "titular": getattr(e, "titular", None),
        "pais": getattr(e, "pais", None),
        "fecha_inscripcion": _fecha,
        "estatus": getattr(e, "estatus", None),
        "page": getattr(e, "page", None) or getattr(e, "pagina", None),
        "is_matcheable": 1 if getattr(e, "matcheable", False) else 0,
        "is_figura": 1 if getattr(e, "es_figura", False) else 0,
        "is_lema": 1 if getattr(e, "es_lema", False) else 0,
        "productos_servicios": getattr(e, "productos_servicios", None),
        "fuente_parsing": getattr(e, "fuente_parsing", None)
        or getattr(e, "fuente", None),
        "source": getattr(e, "source", None),
        "excerpt": getattr(e, "excerpt", None),
        "entry_json": json.dumps(
            {
                k: v for k, v in getattr(e, "__dict__", {}).items()
                if k not in ("page", "pagina", "fecha_inscripcion")
            },
            ensure_ascii=False, default=str,
        ),
    }


def boletin_entry_upsert(
    conn: sqlite3.Connection, boletin_id: int, e: Any
) -> None:
    """Inserta o actualiza (por ``UNIQUE(boletin_id, expediente)``) una marca.

    Usado por Hermes para refinar sin borrar lo ya persistido por el parser.
    No hace ``DELETE`` previo.
    """
    r = _entry_insert_values(boletin_id, e)
    conn.execute(
        "INSERT INTO boletin_entries("
        " boletin_id, expediente, marca, class_nice, clase_especial,"
        " titular, pais, fecha_inscripcion, estatus, page,"
        " is_matcheable, is_figura, is_lema, productos_servicios,"
        " fuente_parsing, source, excerpt, entry_json)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(boletin_id, expediente) DO UPDATE SET"
        " marca=excluded.marca, class_nice=excluded.class_nice,"
        " clase_especial=excluded.clase_especial, titular=excluded.titular,"
        " pais=excluded.pais, fecha_inscripcion=excluded.fecha_inscripcion,"
        " estatus=excluded.estatus, page=excluded.page,"
        " is_matcheable=excluded.is_matcheable,"
        " is_figura=excluded.is_figura, is_lema=excluded.is_lema,"
        " productos_servicios=excluded.productos_servicios,"
        " fuente_parsing=excluded.fuente_parsing, source=excluded.source,"
        " excerpt=excluded.excerpt, entry_json=excluded.entry_json",
        (
            r["boletin_id"], r["expediente"], r["marca"],
            r["class_nice"], r["clase_especial"], r["titular"],
            r["pais"], r["fecha_inscripcion"], r["estatus"],
            r["page"], r["is_matcheable"], r["is_figura"],
            r["is_lema"], r["productos_servicios"],
            r["fuente_parsing"], r["source"], r["excerpt"],
            r["entry_json"],
        ),
    )


def boletines_entries_replace(
    conn: sqlite3.Connection,
    boletin_id: int,
    entries: Iterable[Any],
) -> int:
    """Reemplaza las marcas extraídas de un boletín por las dadas.

    Borra las filas previas del boletín e inserta las nuevas. Devuelve
    cuántas filas se insertaron.
    """
    conn.execute(
        "DELETE FROM boletin_entries WHERE boletin_id = ?", (boletin_id,)
    )
    added = 0
    for e in entries:
        boletin_entry_upsert(conn, boletin_id, e)
        added += 1
    conn.commit()
    return added


def boletines_entries_list(
    conn: sqlite3.Connection, boletin_id: int
) -> list[BoletinEntryRow]:
    rows = conn.execute(
        "SELECT * FROM boletin_entries WHERE boletin_id = ?"
        " ORDER BY class_nice IS NULL, class_nice, marca",
        (boletin_id,),
    ).fetchall()
    return [_entry_from_row(conn, r) for r in rows]


def boletines_list_extracted_for_user(
    conn: sqlite3.Connection, user_id: int
) -> list[BoletinRow]:
    """Boletines del usuario con extracción ya persistida.

    Se usan para el análisis retroactivo de una marca recién cargada en
    watchlist/portafolio: re-leen el ``extraction_json`` (páginas de
    texto) sin volver a extraer el PDF.
    """
    rows = conn.execute(
        "SELECT * FROM boletines"
        " WHERE uploaded_by = ? AND extraction_json IS NOT NULL"
        " ORDER BY id",
        (user_id,),
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
    matched_with: Optional[str] = None


def _detection_from_row(row: sqlite3.Row) -> DetectionRow:
    data = dict(row)
    data.setdefault("matched_with", None)
    return DetectionRow(**data)


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
    matched_with: Optional[str] = None,
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
        " matched_with, pais, fecha_inscripcion, fuente_parsing, es_figura, es_lema)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
            matched_with,
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


def stats_for_user(
    conn: sqlite3.Connection, user_id: int, *, admin_all: bool = False
) -> UserStats:
    def _scalar(sql: str, params: tuple = ()) -> int:
        row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    # Multi-tenant: los boletines se cuentan solo del usuario, salvo que el
    # admin use admin_all=True para ver el total global.
    boletin_scope = "" if admin_all else "WHERE uploaded_by=?"
    boletin_params = () if admin_all else (user_id,)

    return UserStats(
        watchlist_count=_scalar(
            "SELECT COUNT(*) FROM watchlist WHERE user_id=?", (user_id,)
        ),
        portfolio_count=_scalar(
            "SELECT COUNT(*) FROM portfolio WHERE user_id=?", (user_id,)
        ),
        boletines_count=_scalar(
            f"SELECT COUNT(*) FROM boletines {boletin_scope}", boletin_params
        ),
        detections_count=_scalar(
            "SELECT COUNT(*) FROM detections WHERE user_id=?", (user_id,)
        ),
        last_boletin_at=conn.execute(
            f"SELECT MAX(uploaded_at) FROM boletines {boletin_scope}",
            boletin_params,
        ).fetchone()[0],
    )

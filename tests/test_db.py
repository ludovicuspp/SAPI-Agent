"""Tests de la capa de persistencia."""
from __future__ import annotations

import sqlite3

import pytest

from scripts import db


class TestSchema:
    def test_init_db_creates_tables(self, tmp_db):
        rows = tmp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [r["name"] for r in rows]
        for t in (
            "users", "watchlist", "portfolio",
            "boletines", "detections", "scans_log",
        ):
            assert t in names

    def test_init_db_is_idempotent(self, tmp_path):
        f = tmp_path / "x.db"
        db.init_db(f)
        db.init_db(f)  # no debe fallar


class TestMigrationRoleCheck:
    """Migración del CHECK de roles en BD existentes.

    Cubre el bug que rompió prod: el 12-step reconstruía ``users`` con
    FK activas, ``RENAME`` reescribía los ``REFERENCES`` de las tablas
    hijas hacia ``users_legacy`` y el ``DROP`` final fallaba, dejando la
    BD a medias (usuarios desaparecidos, logins 500). Ahora la
    reconstrucción corre con ``foreign_keys=OFF`` y se recupera el
    estado fallido (``users_legacy`` sobrante + hijas apuntando a él).
    """

    OLD_USERS_SQL = (
        "CREATE TABLE IF NOT EXISTS users (\n"
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "    email TEXT NOT NULL UNIQUE,\n"
        "    password_hash TEXT NOT NULL,\n"
        "    role TEXT NOT NULL CHECK (role IN ('admin','agent')),\n"
        "    active INTEGER NOT NULL DEFAULT 1,\n"
        "    created_at TEXT NOT NULL DEFAULT (datetime('now')),\n"
        "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))\n"
        ");"
    )

    NEW_USERS_SQL = (
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

    CHILD_TABLES = (
        "watchlist", "portfolio", "boletines", "detections",
        "scans_log", "portfolio_history",
    )

    def _make_old_db(self, path):
        """BD con el CHECK antiguo (admin,agent) + tablas hijas completas."""
        start = db.SCHEMA_SQL.index("CREATE TABLE IF NOT EXISTS users")
        end = db.SCHEMA_SQL.index("CREATE TABLE IF NOT EXISTS watchlist")
        old_schema = db.SCHEMA_SQL[:start] + self.OLD_USERS_SQL + db.SCHEMA_SQL[end:]
        conn = sqlite3.connect(path)
        conn.executescript(old_schema)
        conn.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (?,?,?)",
            ("admin@x.com", "h1", "admin"),
        )
        conn.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (?,?,?)",
            ("user@x.com", "h2", "agent"),
        )
        conn.execute("INSERT INTO watchlist (user_id, name) VALUES (1, 'ACME')")
        conn.execute("INSERT INTO portfolio (user_id, name) VALUES (1, 'P1')")
        conn.commit()
        conn.close()

    def _assert_migrated(self, conn):
        users = {
            r["email"]: r["role"]
            for r in conn.execute("SELECT email, role FROM users")
        }
        assert users == {"admin@x.com": "admin", "user@x.com": "agent"}
        # El CHECK quedó ampliado: nuevos roles insertables.
        conn.execute(
            "INSERT INTO users (email, password_hash, role, nombre) "
            "VALUES ('p@x.com', 'h', 'empresa', 'P')"
        )
        # Ninguna tabla hija referencia users_legacy.
        for tbl in self.CHILD_TABLES:
            sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone()["sql"]
            assert '"users_legacy"' not in sql, f"{tbl} apunta a users_legacy"
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='users_legacy'"
            ).fetchone()
            is None
        )
        # La fila hija sobrevive con el mismo user_id.
        assert conn.execute(
            "SELECT name FROM watchlist WHERE user_id=1"
        ).fetchone()["name"] == "ACME"
        # Boletines: columnas de progreso Hermes migradas.
        bcols = {
            c[1]
            for c in conn.execute("PRAGMA table_info(boletines)")
        }
        for col in (
            "hermes_progress_step",
            "hermes_progress_current_page",
            "hermes_progress_total_pages",
            "hermes_progress_updated_at",
            "checkpoint_json",
            "processing_batch",
        ):
            assert col in bcols, f"falta columna {col} en boletines"

    def test_old_db_migrates_in_place(self, tmp_path):
        f = tmp_path / "old.db"
        self._make_old_db(f)
        db.init_db(f)
        conn = db.connect(f)
        self._assert_migrated(conn)
        conn.close()

    def test_recovers_from_users_legacy_leftover(self, tmp_path):
        """Simula el 12-step fallido: users_legacy sobrante con los datos
        y tablas hijas cuyos REFERENCES quedaron apuntando a él."""
        f = tmp_path / "legacy.db"
        self._make_old_db(f)
        conn = sqlite3.connect(f)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("ALTER TABLE users RENAME TO users_legacy")
        conn.executescript(self.NEW_USERS_SQL)  # users nueva, vacía
        conn.commit()
        conn.close()
        # En este punto las hijas referencian "users_legacy".
        assert '"users_legacy"' in db.connect(f).execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='watchlist'"
        ).fetchone()["sql"]

        db.init_db(f)

        conn = db.connect(f)
        self._assert_migrated(conn)
        conn.close()


class TestUsers:
    def test_create_and_get(self, tmp_db):
        uid = db.users_create(
            tmp_db, "a@b.c", "hash", role="admin"
        )
        u = db.users_get_by_email(tmp_db, "a@b.c")
        assert u is not None
        assert u.id == uid
        assert u.email == "a@b.c"
        assert u.role == "admin"

    def test_unique_email(self, tmp_db):
        db.users_create(tmp_db, "a@b.c", "h")
        with pytest.raises(Exception):
            db.users_create(tmp_db, "a@b.c", "h")

    def test_count_admins(self, tmp_db):
        assert db.users_count_admins(tmp_db) == 0
        db.users_create(tmp_db, "x@y.z", "h", role="admin")
        db.users_create(tmp_db, "p@y.z", "h", role="agent")
        assert db.users_count_admins(tmp_db) == 1


class TestWatchlist:
    def test_add_and_list(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        db.watchlist_add(tmp_db, uid, "ACME")
        db.watchlist_add(tmp_db, uid, "MARTINEZ")
        items = db.watchlist_list_for_user(tmp_db, uid)
        assert {w.name for w in items} == {"ACME", "MARTINEZ"}

    def test_tenant_isolation(self, tmp_db):
        u1 = db.users_create(tmp_db, "u1@x.y", "h")
        u2 = db.users_create(tmp_db, "u2@x.y", "h")
        db.watchlist_add(tmp_db, u1, "PRIVADA_DE_U1")
        assert db.watchlist_list_for_user(tmp_db, u1)
        assert db.watchlist_list_for_user(tmp_db, u2) == []

    def test_only_active(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        a = db.watchlist_add(tmp_db, uid, "A")
        b = db.watchlist_add(tmp_db, uid, "B")
        db.watchlist_toggle(tmp_db, b, uid, active=False)
        active = db.watchlist_list_for_user(tmp_db, uid, only_active=True)
        assert {w.name for w in active} == {"A"}


class TestPortfolio:
    def test_add_and_list(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        db.portfolio_add(tmp_db, uid, "MARCA PROPIA", expediente="2026-100")
        items = db.portfolio_list_for_user(tmp_db, uid)
        assert len(items) == 1
        assert items[0].expediente == "2026-100"

    def test_update_status(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        pid = db.portfolio_add(tmp_db, uid, "M", expediente="X")
        db.portfolio_update_status(tmp_db, pid, "CONCEDIDA", uid)
        items = db.portfolio_list_for_user(tmp_db, uid)
        assert items[0].status == "CONCEDIDA"
        assert items[0].last_checked_at is not None


class TestBoletines:
    def test_create_and_mark_extracted(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(
            tmp_db, uid, "boletin.pdf", "/tmp/boletin.pdf", "abc123"
        )
        db.boletines_mark_extracted(
            tmp_db,
            boletin_id=bid,
            pages=10,
            extraction_payload={"pages": []},
            bulletin_number=651,
            period="2026-03",
            needs_hermes_review=False,
        )
        b = db.boletines_get(tmp_db, bid)
        assert b is not None
        assert b.status == "extracted"
        assert b.bulletin_number == 651
        assert b.pages == 10

    def test_update_hermes_progress_and_done(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(tmp_db, uid, "b.pdf", "/tmp/b.pdf", "sh")
        db.boletines_mark_extracted(
            tmp_db, bid, 10, {}, None, None, needs_hermes_review=True
        )
        db.boletines_update_hermes_progress(
            tmp_db,
            bid,
            step="analyzing_page",
            current_page=4,
            total_pages=10,
        )
        b = db.boletines_get(tmp_db, bid)
        assert b.hermes_progress_step == "analyzing_page"
        assert b.hermes_progress_current_page == 4
        assert b.hermes_progress_total_pages == 10
        assert b.hermes_progress_updated_at is not None
        assert b.hermes_processed_at is None

        db.boletines_mark_hermes_progress_done(tmp_db, bid)
        b2 = db.boletines_get(tmp_db, bid)
        assert b2.hermes_progress_step == "done"
        assert b2.hermes_progress_current_page == 10
        assert b2.hermes_processed_at is not None

    def test_list_pending_hermes(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        b1 = db.boletines_create(
            tmp_db, uid, "a.pdf", "/tmp/a.pdf", "h1"
        )
        db.boletines_mark_extracted(
            tmp_db, b1, 1, {}, None, None, needs_hermes_review=True
        )
        b2 = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "h2"
        )
        db.boletines_mark_extracted(
            tmp_db, b2, 1, {}, None, None, needs_hermes_review=False
        )
        pending = db.boletines_list_pending_hermes(tmp_db)
        assert len(pending) == 1
        assert pending[0].id == b1

    def test_boletin_entries_replace_and_list(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(
            tmp_db, uid, "b.pdf", "/tmp/b.pdf", "sh"
        )
        db.boletines_mark_extracted(
            tmp_db, bid, 1, {}, None, None, needs_hermes_review=False
        )

        class _E:
            def __init__(self, exp, marca, clase):
                self.expediente = exp
                self.marca = marca
                self.class_nice = clase
                self.clase_especial = None
                self.titular = "Titular A"
                self.pais = "VE"
                self.fecha_inscripcion = "2026-01-01"
                self.estatus = "PUBLICADA"
                self.page = 3
                self.matcheable = True
                self.es_figura = False
                self.es_lema = False
                self.productos_servicios = None
                self.fuente_parsing = "pattern_a"
                self.source = None
                self.excerpt = "exc"

        n = db.boletines_entries_replace(
            tmp_db, bid, [_E("EXP-1", "Alpha", 5), _E("EXP-2", "Beta", 9)]
        )
        tmp_db.commit()
        assert n == 2
        rows = db.boletines_entries_list(tmp_db, bid)
        assert len(rows) == 2
        by_exp = {r.expediente: r for r in rows}
        assert by_exp["EXP-1"].marca == "Alpha"
        assert by_exp["EXP-1"].class_nice == 5
        assert by_exp["EXP-1"].titular == "Titular A"
        assert by_exp["EXP-1"].is_matcheable == 1

        # Reemplazo: elimina las viejas y deja solo las nuevas.
        n2 = db.boletines_entries_replace(
            tmp_db, bid, [_E("EXP-3", "Gamma", 12)]
        )
        tmp_db.commit()
        assert n2 == 1
        rows2 = db.boletines_entries_list(tmp_db, bid)
        assert len(rows2) == 1
        assert rows2[0].expediente == "EXP-3"

    def test_boletin_entry_harmonizes_hermes_shape(self, tmp_db):
        """El upsert acepta el shape de Hermes (clase_niza/pagina/fuente)."""
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(tmp_db, uid, "b.pdf", "/tmp/b.pdf", "sh")

        class _H:
            expediente = "H-1"
            marca = "Marca Hermes"
            clase_niza = 25
            titular = "Titular"
            pais = "CO"
            estatus = "CONCEDIDA"
            pagina = 7
            fuente = "hermes_vision"
            confianza = "medium"
            excerpt = "x"
            fecha_inscripcion = "2026-02-02"

        db.boletin_entry_upsert(tmp_db, bid, _H())
        tmp_db.commit()
        rows = db.boletines_entries_list(tmp_db, bid)
        assert len(rows) == 1
        r = rows[0]
        assert r.class_nice == 25
        assert r.page == 7
        assert r.fuente_parsing == "hermes_vision"
        assert r.marca == "Marca Hermes"

        # Idempotencia por (boletin_id, expediente): actualiza, no duplica.
        db.boletin_entry_upsert(tmp_db, bid, _H())
        tmp_db.commit()
        assert len(db.boletines_entries_list(tmp_db, bid)) == 1


class TestDetections:
    def test_add_and_list(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(tmp_db, uid, "p.pdf", "/tmp/p.pdf", "h")
        db.detections_add(
            tmp_db,
            boletin_id=bid,
            user_id=uid,
            mark_name="ACME",
            similarity=0.95,
            match_kind="similar",
            source="pdfplumber_text",
            confidence="high",
        )
        items = db.detections_list_for_user(tmp_db, uid)
        assert len(items) == 1
        assert items[0].mark_name == "ACME"
        assert items[0].matched_with is None

    def test_add_with_matched_with(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(tmp_db, uid, "p.pdf", "/tmp/p.pdf", "h")
        wid = db.watchlist_add(tmp_db, uid, "ACME")
        db.detections_add(
            tmp_db,
            boletin_id=bid,
            user_id=uid,
            watchlist_id=wid,
            mark_name="ACME SHOP",
            matched_with="ACME",
            similarity=0.9,
            match_kind="similar",
            source="pdfplumber_text",
            confidence="high",
        )
        items = db.detections_list_for_user(tmp_db, uid)
        assert items[0].matched_with == "ACME"

    def test_migrate_backfill_matched_with(self, tmp_path):
        """La migración rellena matched_with desde watchlist/portfolio."""
        from scripts import db
        db_file = tmp_path / "mig.db"
        db.init_db(db_file)
        conn = db.connect(db_file)
        uid = db.users_create(conn, "u@x.y", "h")
        bid = db.boletines_create(conn, uid, "p.pdf", "/tmp/p.pdf", "h")
        wid = db.watchlist_add(conn, uid, "MI MARCA")
        pid = db.portfolio_add(conn, uid, "MARCA PROPIA")
        # Insertar filas con matched_with explícitamente NULL (como BD vieja).
        conn.execute(
            "INSERT INTO detections"
            " (boletin_id,user_id,watchlist_id,portfolio_id,mark_name,similarity,"
            "  match_kind,source,confidence,matched_with) VALUES"
            " (?,?,?,NULL,'X',0.9,'similar','pdfplumber_text','high',NULL)",
            (bid, uid, wid),
        )
        conn.execute(
            "INSERT INTO detections"
            " (boletin_id,user_id,watchlist_id,portfolio_id,mark_name,similarity,"
            "  match_kind,source,confidence,matched_with) VALUES"
            " (?,?,NULL,?,'X',0.9,'own_status','pdfplumber_text','high',NULL)",
            (bid, uid, pid),
        )
        conn.commit()
        conn.close()
        # Re-ejecutar init_db para disparar el backfill (idempotente).
        db.init_db(db_file)
        conn = db.connect(db_file)
        rows = conn.execute(
            "SELECT matched_with, watchlist_id, portfolio_id FROM detections ORDER BY id"
        ).fetchall()
        by_origin = {("w" if r[1] is not None else "p"): r[0] for r in rows}
        assert by_origin["w"] == "MI MARCA"
        assert by_origin["p"] == "MARCA PROPIA"
        conn.close()

    def test_mark_notified(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(tmp_db, uid, "p.pdf", "/tmp/p.pdf", "h")
        did = db.detections_add(
            tmp_db,
            boletin_id=bid,
            user_id=uid,
            mark_name="X",
            similarity=0.9,
            match_kind="similar",
            source="pdfplumber_text",
            confidence="high",
        )
        pending = db.detections_pending_notification(tmp_db, uid)
        assert len(pending) == 1
        db.detections_mark_notified(tmp_db, [did])
        assert db.detections_pending_notification(tmp_db, uid) == []


class TestScansLog:
    def test_record(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        sid = db.scans_log_record(
            tmp_db, kind="extract", status="ok", user_id=uid, duration_ms=42
        )
        assert sid > 0
        row = tmp_db.execute(
            "SELECT * FROM scans_log WHERE id=?", (sid,)
        ).fetchone()
        assert row["kind"] == "extract"
        assert row["duration_ms"] == 42


class TestStats:
    def test_stats_for_user(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        db.watchlist_add(tmp_db, uid, "A")
        db.portfolio_add(tmp_db, uid, "P")
        s = db.stats_for_user(tmp_db, uid)
        assert s.watchlist_count == 1
        assert s.portfolio_count == 1
        assert s.boletines_count == 0
        assert s.detections_count == 0

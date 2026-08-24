"""Tests de la capa de persistencia."""
from __future__ import annotations

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

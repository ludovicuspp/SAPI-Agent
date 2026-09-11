"""Tests de Fase 4: cola de verificación Hermes de conflictos.

Cubre la política de candidatos (``hermes_policy``), las funciones de BD
(cola, veredicto, undo, filtros) y los endpoints de la API
(``verify-queue``, ``verify``, ``undo-verdict``).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterator

from fastapi.testclient import TestClient
import pytest

from scripts import auth, db
from scripts.config import Settings, get_settings
from scripts.lapsos import DEFAULT_LAPSOS, rebuild_alerts_for_boletin
from scripts.matcher.hermes_policy import should_hermes_verify


# ── Fixtures (patrón de tests/test_api.py) ──────────────────────


@pytest.fixture(autouse=True)
def _patch_settings(tmp_path: Path):
    """Settings aisladas: BD temporal + JWT conocida + sin token Hermes."""
    db_file = tmp_path / "test_verify.db"
    db.init_db(db_file)
    os.environ["SAPI_DB_PATH"] = str(db_file)
    os.environ["JWT_SECRET"] = "test-verify-secret"
    os.environ["JWT_EXPIRES_MIN"] = "60"
    os.environ["UPLOADS_DIR"] = str(tmp_path / "uploads")
    os.environ["SERVICE_TOKEN_HERMES"] = ""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def uid(tmp_db: sqlite3.Connection) -> int:
    return db.users_create(tmp_db, "verify@x.y", "h")


@pytest.fixture()
def admin(tmp_db: sqlite3.Connection) -> db.UserRow:
    uid_ = db.users_create(tmp_db, "admin@example.com", "h", "admin")
    tmp_db.commit()
    return db.users_get(tmp_db, uid_)


@pytest.fixture()
def agent_user(tmp_db: sqlite3.Connection) -> db.UserRow:
    uid_ = db.users_create(tmp_db, "agent@example.com", "h", "agent")
    tmp_db.commit()
    return db.users_get(tmp_db, uid_)


@pytest.fixture()
def client(tmp_db: sqlite3.Connection) -> Iterator[TestClient]:
    """TestClient con BD override."""
    from api.main import create_app
    from api.deps import get_db

    app = create_app()

    def _override_get_db():
        yield tmp_db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c


def _token_for(user: db.UserRow) -> str:
    cfg = Settings()
    return auth.create_access_token(
        user.id, user.role, secret=cfg.jwt_secret, expires_min=cfg.jwt_expires_min,
    )


# ── Política ────────────────────────────────────────────────────


class TestHermesPolicy:
    def test_short_mark_flags(self):
        assert should_hermes_verify(
            source="pdfplumber_text", match_kind="conflict",
            confidence="high", mark_name="X",
        )
        assert should_hermes_verify(
            source="pdfplumber_text", match_kind="similar",
            confidence="high", mark_name="3XM",
        )

    def test_medium_low_confidence_flags(self):
        assert should_hermes_verify(
            source="pdfplumber_text", match_kind="conflict",
            confidence="medium", mark_name="RAPTORFLEX",
        )
        assert should_hermes_verify(
            source="pdfplumber_text", match_kind="conflict",
            confidence="low", mark_name="DRON",
        )

    def test_family_match_flags(self):
        assert should_hermes_verify(
            source="pdfplumber_text", match_kind="conflict",
            confidence="high", mark_name="DRAGON WINCH", is_family=True,
        )

    def test_high_confidence_long_non_family_no(self):
        assert not should_hermes_verify(
            source="pdfplumber_text", match_kind="conflict",
            confidence="high", mark_name="RAPTORFLEX",
        )

    def test_own_status_never(self):
        assert not should_hermes_verify(
            source="pdfplumber_text", match_kind="own_status",
            confidence="low", mark_name="X",
        )

    def test_hermes_source_never(self):
        assert not should_hermes_verify(
            source="hermes_vision", match_kind="conflict",
            confidence="medium", mark_name="X",
        )


# ── BD: cola, veredicto, undo y filtros ─────────────────────────


@pytest.fixture()
def uid(tmp_db: sqlite3.Connection) -> int:
    return db.users_create(tmp_db, "verify@x.y", "h")


def _boletin(tmp_db: sqlite3.Connection, uid: int, *, number: int = 652) -> int:
    bid = db.boletines_create(tmp_db, uid, "BPI.pdf", "/tmp/x.pdf", "sha")
    tmp_db.execute(
        "UPDATE boletines SET bulletin_number=?, fecha_publicacion=? WHERE id=?",
        (number, "2026-01-05", bid),
    )
    tmp_db.commit()
    return bid


def _det(
    tmp_db: sqlite3.Connection,
    uid: int,
    bid: int,
    *,
    marca: str = "X",
    confidence: str = "medium",
    flag: bool = True,
) -> int:
    return db.detections_add(
        tmp_db,
        boletin_id=bid,
        user_id=uid,
        mark_name=marca,
        similarity=0.9,
        match_kind="conflict",
        source="pdfplumber_text",
        confidence=confidence,
        needs_hermes_reverify=1 if flag else 0,
    )


class TestVerifyDbFunctions:
    def test_queue_lists_only_flagged_unverified(self, tmp_db: sqlite3.Connection, uid: int):
        bid = _boletin(tmp_db, uid)
        d1 = _det(tmp_db, uid, bid, marca="X")
        d2 = _det(tmp_db, uid, bid, marca="LARGA", confidence="high", flag=False)
        tmp_db.commit()
        queue = db.detections_verify_queue(tmp_db)
        assert [q["id"] for q in queue] == [d1]
        assert queue[0]["boletin_number"] == 652

    def test_verify_discarded_discards_alerts(self, tmp_db: sqlite3.Connection, uid: int):
        bid = _boletin(tmp_db, uid)
        did = _det(tmp_db, uid, bid, marca="X")
        # Alerta de lapso pendiente para esa detección.
        db.lapse_config_seed(tmp_db, DEFAULT_LAPSOS)
        tmp_db.execute(
            "UPDATE detections SET tipo_disposicion='CONCESION' WHERE id=?",
            (did,),
        )
        rebuild_alerts_for_boletin(tmp_db, bid)
        tmp_db.commit()
        assert db.alerts_list_for_user(tmp_db, uid)[0].estado == "pendiente"

        updated = db.detections_verify_set(tmp_db, did, "discarded", "marca corta")
        tmp_db.commit()
        assert updated.hermes_verdict == "discarded"
        assert updated.hermes_reason == "marca corta"
        alerta = db.alerts_list_for_user(tmp_db, uid)[0]
        assert alerta.estado == "descartada"

    def test_verify_confirmed_keeps_alerts(self, tmp_db: sqlite3.Connection, uid: int):
        bid = _boletin(tmp_db, uid)
        did = _det(tmp_db, uid, bid, marca="X")
        db.lapse_config_seed(tmp_db, DEFAULT_LAPSOS)
        tmp_db.execute(
            "UPDATE detections SET tipo_disposicion='CONCESION' WHERE id=?",
            (did,),
        )
        rebuild_alerts_for_boletin(tmp_db, bid)
        tmp_db.commit()

        db.detections_verify_set(tmp_db, did, "confirmed", "conflicto real")
        tmp_db.commit()
        assert db.alerts_list_for_user(tmp_db, uid)[0].estado == "pendiente"

    def test_undo_verdict_restores_alerts(self, tmp_db: sqlite3.Connection, uid: int):
        bid = _boletin(tmp_db, uid)
        did = _det(tmp_db, uid, bid, marca="X")
        db.lapse_config_seed(tmp_db, DEFAULT_LAPSOS)
        tmp_db.execute(
            "UPDATE detections SET tipo_disposicion='CONCESION' WHERE id=?",
            (did,),
        )
        rebuild_alerts_for_boletin(tmp_db, bid)
        db.detections_verify_set(tmp_db, did, "discarded", "fp")
        tmp_db.commit()
        assert db.alerts_list_for_user(tmp_db, uid)[0].estado == "descartada"

        restored = db.detections_verify_clear(tmp_db, did)
        tmp_db.commit()
        assert restored.hermes_verdict is None
        alerta = db.alerts_list_for_user(tmp_db, uid)[0]
        assert alerta.estado == "pendiente"
        assert alerta.resolved_at is None

    def test_list_excludes_discarded_unless_requested(self, tmp_db: sqlite3.Connection, uid: int):
        bid = _boletin(tmp_db, uid)
        d1 = _det(tmp_db, uid, bid, marca="X")
        _det(tmp_db, uid, bid, marca="Y")
        db.detections_verify_set(tmp_db, d1, "discarded", "fp")
        tmp_db.commit()
        visible = db.detections_list_for_user(tmp_db, uid)
        assert [d.id for d in visible] == [d1 + 1]
        all_rows = db.detections_list_for_user(tmp_db, uid, include_discarded=True)
        assert {d.id for d in all_rows} == {d1, d1 + 1}

    def test_detections_for_portfolio_excludes_discarded(self, tmp_db: sqlite3.Connection, uid: int):
        pid = db.portfolio_add(tmp_db, user_id=uid, name="RAPTORFLEX")
        bid = _boletin(tmp_db, uid)
        d1 = db.detections_add(
            tmp_db, boletin_id=bid, user_id=uid, portfolio_id=pid,
            mark_name="X", similarity=0.9, match_kind="conflict",
            source="pdfplumber_text", confidence="medium",
            needs_hermes_reverify=1,
        )
        db.detections_verify_set(tmp_db, d1, "discarded", "fp")
        tmp_db.commit()
        hits = db.detections_for_portfolio(tmp_db, pid, uid)
        assert hits == []


# ── API ─────────────────────────────────────────────────────────


@pytest.fixture()
def hermes_env():
    os.environ["SERVICE_TOKEN_HERMES"] = "valid-hermes-token"
    get_settings.cache_clear()
    yield
    os.environ["SERVICE_TOKEN_HERMES"] = ""
    get_settings.cache_clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_data(tmp_db: sqlite3.Connection, uid: int) -> tuple[int, int]:
    bid = _boletin(tmp_db, uid)
    did = _det(tmp_db, uid, bid, marca="X")
    other_bid = _boletin(tmp_db, uid, number=653)
    other_did = _det(tmp_db, uid, other_bid, marca="Y")
    tmp_db.commit()
    return did, other_did


class TestVerifyApi:
    def test_queue_requires_hermes_token(self, client: TestClient) -> None:
        r = client.get("/api/detections/verify-queue")
        assert r.status_code in (403, 503)

    def test_queue_rejects_wrong_token(self, client: TestClient, hermes_env):
        r = client.get(
            "/api/detections/verify-queue",
            headers={"X-Hermes-Token": "wrong"},
        )
        assert r.status_code == 403

    def test_queue_lists_candidates(
        self, client: TestClient, tmp_db: sqlite3.Connection, agent_user: db.UserRow, hermes_env
    ):
        _setup_data(tmp_db, agent_user.id)
        r = client.get(
            "/api/detections/verify-queue",
            headers={"X-Hermes-Token": "valid-hermes-token"},
        )
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 2
        assert items[0]["mark_name"] == "X"
        assert items[0]["boletin_number"] == "652"

    def test_verify_discarded_hides_and_discards_alert(
        self, client: TestClient, tmp_db: sqlite3.Connection, agent_user: db.UserRow, hermes_env
    ):
        did, _ = _setup_data(tmp_db, agent_user.id)
        bid = tmp_db.execute("SELECT boletin_id FROM detections WHERE id=?", (did,)).fetchone()["boletin_id"]
        db.lapse_config_seed(tmp_db, DEFAULT_LAPSOS)
        tmp_db.execute("UPDATE detections SET tipo_disposicion='CONCESION' WHERE id=?", (did,))
        rebuild_alerts_for_boletin(tmp_db, bid)
        tmp_db.commit()
        assert db.alerts_list_for_user(tmp_db, agent_user.id)[0].estado == "pendiente"

        r = client.post(
            f"/api/detections/{did}/verify",
            json={"verdict": "discarded", "reason": "marca corta"},
            headers={"X-Hermes-Token": "valid-hermes-token"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["hermes_verdict"] == "discarded"
        assert body["hermes_reason"] == "marca corta"
        assert db.alerts_list_for_user(tmp_db, agent_user.id)[0].estado == "descartada"

        # Fuera del listado accionable por defecto; visible con flag.
        visible = db.detections_list_for_user(tmp_db, agent_user.id)
        assert did not in [d.id for d in visible]
        all_rows = db.detections_list_for_user(tmp_db, agent_user.id, include_discarded=True)
        assert did in [d.id for d in all_rows]

    def test_verify_confirmed_ok(self, client: TestClient, tmp_db: sqlite3.Connection, agent_user: db.UserRow, hermes_env):
        did, _ = _setup_data(tmp_db, agent_user.id)
        r = client.post(
            f"/api/detections/{did}/verify",
            json={"verdict": "confirmed", "reason": "conflicto real"},
            headers={"X-Hermes-Token": "valid-hermes-token"},
        )
        assert r.status_code == 200
        assert r.json()["hermes_verdict"] == "confirmed"
        ids = [d.id for d in db.detections_list_for_user(tmp_db, agent_user.id)]
        assert did in ids

    def test_verify_missing_id_404(self, client: TestClient, hermes_env):
        r = client.post(
            "/api/detections/999999/verify",
            json={"verdict": "confirmed", "reason": "x"},
            headers={"X-Hermes-Token": "valid-hermes-token"},
        )
        assert r.status_code == 404

    def test_verify_rejects_empty_reason(self, client: TestClient, tmp_db: sqlite3.Connection, agent_user: db.UserRow, hermes_env):
        did, _ = _setup_data(tmp_db, agent_user.id)
        r = client.post(
            f"/api/detections/{did}/verify",
            json={"verdict": "discarded", "reason": ""},
            headers={"X-Hermes-Token": "valid-hermes-token"},
        )
        assert r.status_code == 422

    def test_undo_owner_and_multi_tenant(self, client: TestClient, tmp_db: sqlite3.Connection, admin: db.UserRow):
        other_uid = db.users_create(tmp_db, "other@x.y", "h")
        bid = _boletin(tmp_db, other_uid)
        did = _det(tmp_db, other_uid, bid)
        tmp_db.commit()
        db.detections_verify_set(tmp_db, did, "discarded", "fp")
        tmp_db.commit()
        # Admin puede deshacer aunque no sea el dueño.
        r = client.post(f"/api/detections/{did}/undo-verdict", headers=_auth(_token_for(admin)))
        assert r.status_code == 200
        row = tmp_db.execute("SELECT hermes_verdict FROM detections WHERE id=?", (did,)).fetchone()
        assert row["hermes_verdict"] is None

    def test_undo_rejects_other_user(self, client: TestClient, tmp_db: sqlite3.Connection, admin: db.UserRow, agent_user: db.UserRow):
        did = _det(tmp_db, admin.id, _boletin(tmp_db, admin.id))
        tmp_db.commit()
        r = client.post(f"/api/detections/{did}/undo-verdict", headers=_auth(_token_for(agent_user)))
        assert r.status_code == 403
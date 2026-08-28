"""Tests de integración para la API FastAPI."""
from __future__ import annotations

import sqlite3
import io
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from scripts import auth, db
from scripts.config import Settings
from api.main import create_app
from api.deps import get_db


# Fixtures específicos de este archivo para no depender de conftest.py.


@pytest.fixture(autouse=True)
def _patch_settings(tmp_path: Path):
    """Override de Settings para tests: BD temporal + JWT secret conocido."""
    db_file = tmp_path / "test.db"
    db.init_db(db_file)
    # Configurar entorno antes de que Settings se instancie
    import os
    os.environ["SAPI_DB_PATH"] = str(db_file)
    os.environ["JWT_SECRET"] = "test-secret-for-tests"
    os.environ["JWT_EXPIRES_MIN"] = "60"
    os.environ["UPLOADS_DIR"] = str(tmp_path / "uploads")
    os.environ["SERVICE_TOKEN_HERMES"] = ""
    # Forzar recálculo del lru_cache de get_settings
    from scripts.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """BD SQLite temporal con esquema completo."""
    db_file = tmp_path / "test_api.db"
    db.init_db(db_file)
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    yield conn
    conn.close()


@pytest.fixture()
def client(tmp_db: sqlite3.Connection) -> Iterator[TestClient]:
    """TestClient con BD override."""
    app = create_app()

    def _override_get_db():
        yield tmp_db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin(tmp_db: sqlite3.Connection) -> db.UserRow:
    """Crea usuario admin de prueba."""
    pwd_hash = auth.hash_password("admin123456")
    uid = db.users_create(tmp_db, "admin@example.com", pwd_hash, "admin")
    tmp_db.commit()
    return db.users_get(tmp_db, uid)


@pytest.fixture()
def agent_user(tmp_db: sqlite3.Connection) -> db.UserRow:
    """Crea usuario agent de prueba."""
    pwd_hash = auth.hash_password("agent123456")
    uid = db.users_create(tmp_db, "agent@example.com", pwd_hash, "agent")
    tmp_db.commit()
    return db.users_get(tmp_db, uid)


@pytest.fixture()
def admin_token(admin: db.UserRow) -> str:
    """JWT para el admin."""
    cfg = Settings()
    return auth.create_access_token(
        admin.id, admin.role, secret=cfg.jwt_secret, expires_min=cfg.jwt_expires_min,
    )


@pytest.fixture()
def agent_token(agent_user: db.UserRow) -> str:
    """JWT para el agent."""
    cfg = Settings()
    return auth.create_access_token(
        agent_user.id, agent_user.role, secret=cfg.jwt_secret, expires_min=cfg.jwt_expires_min,
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Health ───────────────────────────────────────────────────────


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Auth ─────────────────────────────────────────────────────────


def test_login_success(client: TestClient, admin: db.UserRow):
    r = client.post("/api/auth/login", json={
        "email": "admin@example.com",
        "password": "admin123456",
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient, admin: db.UserRow):
    r = client.post("/api/auth/login", json={
        "email": "admin@example.com",
        "password": "wrong",
    })
    assert r.status_code == 401


def test_login_nonexistent(client: TestClient):
    r = client.post("/api/auth/login", json={
        "email": "nobody@example.com",
        "password": "xxx",
    })
    assert r.status_code == 401


# ── Users ────────────────────────────────────────────────────────


def test_users_list_admin(client: TestClient, admin_token: str):
    r = client.get("/api/users", headers=_auth_header(admin_token))
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_users_list_agent_denied(client: TestClient, agent_token: str):
    r = client.get("/api/users", headers=_auth_header(agent_token))
    assert r.status_code == 403


def test_users_create(client: TestClient, admin_token: str):
    r = client.post("/api/users", json={
        "email": "new@example.com",
        "password": "newpass123456",
        "role": "agent",
    }, headers=_auth_header(admin_token))
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "new@example.com"
    assert data["role"] == "agent"


# ── Watchlist ────────────────────────────────────────────────────


def test_watchlist_add_and_list(client: TestClient, agent_token: str):
    r = client.post("/api/watchlist", json={
        "name": "IRONFLEX",
        "class_nice": 25,
        "notes": "test",
    }, headers=_auth_header(agent_token))
    assert r.status_code == 201
    wl_id = r.json()["id"]

    r = client.get("/api/watchlist", headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert len(r.json()) >= 1
    assert any(w["id"] == wl_id for w in r.json())


def test_watchlist_deactivate(client: TestClient, agent_token: str):
    r = client.post("/api/watchlist", json={"name": "TEST"}, headers=_auth_header(agent_token))
    wl_id = r.json()["id"]
    r = client.delete(f"/api/watchlist/{wl_id}", headers=_auth_header(agent_token))
    assert r.status_code == 204


def test_watchlist_isolation(client: TestClient, agent_token: str, admin_token: str):
    client.post("/api/watchlist", json={"name": "IRONFLEX"}, headers=_auth_header(agent_token))
    r = client.get("/api/watchlist", headers=_auth_header(admin_token))
    assert r.status_code == 200
    assert len(r.json()) == 0


# ── Portfolio ────────────────────────────────────────────────────


def test_portfolio_add_and_list(client: TestClient, agent_token: str):
    r = client.post("/api/portfolio", json={
        "name": "CROCS",
        "expediente": "2015-016216",
        "class_nice": 25,
    }, headers=_auth_header(agent_token))
    assert r.status_code == 201
    r = client.get("/api/portfolio", headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert len(r.json()) >= 1


# ── Boletines ────────────────────────────────────────────────────


def test_boletines_empty_list(client: TestClient, agent_token: str):
    r = client.get("/api/boletines", headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert r.json() == []


def test_boletines_not_found(client: TestClient, agent_token: str):
    r = client.get("/api/boletines/999", headers=_auth_header(agent_token))
    assert r.status_code == 404


# ── Detections ───────────────────────────────────────────────────


def test_detections_empty_list(client: TestClient, agent_token: str):
    r = client.get("/api/detections", headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert r.json() == []


# ── Summary ──────────────────────────────────────────────────────


def test_summary(client: TestClient, agent_token: str):
    r = client.get("/api/summary", headers=_auth_header(agent_token))
    assert r.status_code == 200
    data = r.json()
    assert "watchlist_count" in data
    assert "portfolio_count" in data
    assert "detections_count" in data


# ── Protected endpoints ─────────────────────────────────────────


def test_protected_no_token(client: TestClient):
    r = client.get("/api/watchlist")
    assert r.status_code == 422 or r.status_code == 401


def test_protected_invalid_token(client: TestClient):
    r = client.get("/api/watchlist", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401


# ── Upload ───────────────────────────────────────────────────────


def test_upload_not_pdf(client: TestClient, agent_token: str):
    r = client.post(
        "/api/boletines/upload",
        files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=_auth_header(agent_token),
    )
    assert r.status_code == 400


def test_upload_empty_file(client: TestClient, agent_token: str):
    r = client.post(
        "/api/boletines/upload",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        headers=_auth_header(agent_token),
    )
    assert r.status_code == 400


def test_upload_too_large(client: TestClient, agent_token: str):
    big = io.BytesIO(b"%" * (301 * 1024 * 1024))
    r = client.post(
        "/api/boletines/upload",
        files={"file": ("big.pdf", big, "application/pdf")},
        headers=_auth_header(agent_token),
    )
    assert r.status_code == 413


def test_upload_valid_pdf(client: TestClient, agent_token: str):
    """Upload de PDF real + verificación de status."""
    r = client.post(
        "/api/boletines/upload",
        files={"file": ("boletin.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")},
        headers=_auth_header(agent_token),
    )
    assert r.status_code == 202
    data = r.json()
    assert data["status"] == "extracting"
    boletin_id = data["boletin_id"]

    # Poll status (sin background task real, quedará en 'extracting' o fallará)
    r = client.get(f"/api/boletines/{boletin_id}", headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert r.json()["status"] in ("extracting", "failed")


def test_upload_no_duplica_fila(tmp_path: Path, monkeypatch):
    """El background task del upload NO debe crear una segunda fila en BD.

    Antes del fix, ``processor.process_pdf`` creaba su propia fila,
    resultando en 2 filas por upload (la del endpoint quedaba huérfana
    en 'extracting' para siempre).
    """
    from api.main import create_app
    from api.deps import get_db as get_db_dep
    from scripts import db as dbmod
    db_file = tmp_path / "test_upload_nodup.db"
    dbmod.init_db(db_file)
    monkeypatch.setenv("SAPI_DB_PATH", str(db_file))
    monkeypatch.setenv("JWT_SECRET", "test-nodup")
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    from scripts.config import get_settings
    get_settings.cache_clear()

    app = create_app()

    admin_id = None
    conn = dbmod.connect(db_file)
    admin_id = dbmod.users_create(
        conn, "admin@nodup.local", auth.hash_password("admin1234"), role="admin",
    )
    conn.commit()
    conn.close()

    def _override():
        c = dbmod.connect(db_file)
        try:
            yield c
        finally:
            c.close()
    app.dependency_overrides[get_db_dep] = _override
    cli = TestClient(app)

    token = auth.create_access_token(
        admin_id, "admin",
        secret="test-nodup", expires_min=60,
    )
    r = cli.post(
        "/api/boletines/upload",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 202
    bid = r.json()["boletin_id"]

    # Forzar el background task a ejecutarse sincrónicamente
    from api.routers.uploads import _process_boletin_task
    # Leer el path que el endpoint guardó
    conn = dbmod.connect(db_file)
    bol = dbmod.boletines_get(conn, bid)
    conn.close()
    _process_boletin_task(bid, bol.file_path, admin_id)

    # Ahora solo debe haber UNA fila en boletines con ese SHA
    conn = dbmod.connect(db_file)
    rows = conn.execute(
        "SELECT id, status FROM boletines WHERE file_sha256=?",
        (bol.file_sha256,),
    ).fetchall()
    assert len(rows) == 1, f"Esperaba 1 fila, encontré {len(rows)}: {rows}"
    assert rows[0]["id"] == bid
    assert rows[0]["status"] in ("extracted", "failed")  # NO debe seguir 'extracting'
    conn.close()


# ── Structured (Hermes) ─────────────────────────────────────────


def test_structured_no_hermes_token(client: TestClient, tmp_db: sqlite3.Connection):
    """Sin token de Hermes configurado → 503."""
    uid = db.users_create(tmp_db, "u@example.com", auth.hash_password("pass123456"))
    bid = db.boletines_create(tmp_db, uid, "test.pdf", "/tmp/test.pdf", "abc")
    tmp_db.commit()
    r = client.post(f"/api/boletines/{bid}/structured", json={
        "boletin_id": bid,
        "entries": [{"expediente": "2025-0001", "marca": "TEST", "clase_niza": 25,
                      "titular": "X", "estatus": "PUBLICADA"}],
    })
    assert r.status_code in (401, 403, 422, 503)


def test_structured_wrong_token(client: TestClient, tmp_db: sqlite3.Connection):
    """Token incorrecto → 403."""
    uid = db.users_create(tmp_db, "u@example.com", auth.hash_password("pass123456"))
    bid = db.boletines_create(tmp_db, uid, "test.pdf", "/tmp/test.pdf", "abc")
    tmp_db.commit()
    r = client.post(
        f"/api/boletines/{bid}/structured",
        json={"boletin_id": bid, "entries": [
            {"expediente": "2025-0001", "marca": "TEST", "clase_niza": 25,
             "titular": "X", "estatus": "PUBLICADA"},
        ]},
        headers={"X-Hermes-Token": "wrong-token"},
    )
    assert r.status_code in (403, 503)

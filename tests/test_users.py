"""Tests del CRUD de users (/api/users) + guards de seguridad."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from scripts import auth, db
from scripts.config import Settings, get_settings
from api.main import create_app
from api.deps import get_db


@pytest.fixture(autouse=True)
def _patch_settings(tmp_path: Path):
    db_file = tmp_path / "test_users.db"
    db.init_db(db_file)
    import os
    os.environ["SAPI_DB_PATH"] = str(db_file)
    os.environ["JWT_SECRET"] = "test-secret-for-users"
    os.environ["JWT_EXPIRES_MIN"] = "60"
    os.environ["UPLOADS_DIR"] = str(tmp_path / "uploads")
    os.environ["SERVICE_TOKEN_HERMES"] = ""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    db_file = tmp_path / "test_users_api.db"
    db.init_db(db_file)
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    yield conn
    conn.close()


@pytest.fixture()
def client(tmp_db: sqlite3.Connection) -> Iterator[TestClient]:
    app = create_app()

    def _override_get_db():
        yield tmp_db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c


def _mk_user(tmp_db: sqlite3.Connection, email: str, password: str, role: str) -> db.UserRow:
    uid = db.users_create(tmp_db, email, auth.hash_password(password), role)
    tmp_db.commit()
    return db.users_get(tmp_db, uid)


@pytest.fixture()
def admin(tmp_db: sqlite3.Connection) -> db.UserRow:
    return _mk_user(tmp_db, "admin@example.com", "admin123456", "admin")


@pytest.fixture()
def second_admin(tmp_db: sqlite3.Connection) -> db.UserRow:
    return _mk_user(tmp_db, "admin2@example.com", "admin2123456", "admin")


@pytest.fixture()
def agent_user(tmp_db: sqlite3.Connection) -> db.UserRow:
    return _mk_user(tmp_db, "agent@example.com", "agent123456", "agent")


def _make_token(user: db.UserRow) -> str:
    cfg = Settings()
    return auth.create_access_token(
        user.id, user.role, secret=cfg.jwt_secret, expires_min=cfg.jwt_expires_min,
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── DELETE /api/users/{id} ───────────────────────────────────────


def test_delete_user_success(client: TestClient, admin, second_admin, tmp_db):
    r = client.delete(
        f"/api/users/{second_admin.id}", headers=_auth_header(_make_token(admin)),
    )
    assert r.status_code == 204
    row = tmp_db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE id=?", (second_admin.id,),
    ).fetchone()
    assert row["c"] == 0


def test_delete_user_removes_watchlist_in_cascade(
    client: TestClient, admin, agent_user, tmp_db,
):
    db.watchlist_add(tmp_db, agent_user.id, "MARCA A")
    tmp_db.commit()
    r = client.delete(
        f"/api/users/{agent_user.id}", headers=_auth_header(_make_token(admin)),
    )
    assert r.status_code == 204
    assert tmp_db.execute(
        "SELECT COUNT(*) AS c FROM watchlist WHERE user_id=?", (agent_user.id,),
    ).fetchone()["c"] == 0
    assert tmp_db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE id=?", (agent_user.id,),
    ).fetchone()["c"] == 0


def test_delete_user_detaches_boletines(
    client: TestClient, admin, agent_user, tmp_db,
):
    bid = db.boletines_create(tmp_db, agent_user.id, "b.pdf", "/tmp/b.pdf", "h")
    r = client.delete(
        f"/api/users/{agent_user.id}", headers=_auth_header(_make_token(admin)),
    )
    assert r.status_code == 204
    row = tmp_db.execute(
        "SELECT uploaded_by FROM boletines WHERE id=?", (bid,),
    ).fetchone()
    assert row["uploaded_by"] is None  # boletín se conserva, desligado del usuario


def test_delete_user_not_found(client: TestClient, admin):
    r = client.delete("/api/users/9999", headers=_auth_header(_make_token(admin)))
    assert r.status_code == 404


def test_delete_last_admin_blocked(client: TestClient, admin, tmp_db):
    """Borrar a un admin dejando a 0 admins activos no se permite.

    El endpoint auto-bloquea: ``self`` → 409 antes de llegar al conteo;
    la rama 422 es defensiva (protegida por ``users_count_admins <= 1``).
    Aquí cubrimos: (1) self-delete → 409, (2) con dos admins borrar al
    segundo deja uno (204), (3) el conteo refleja el cambio.
    """
    # 1) self-delete bloquea.
    r = client.delete(f"/api/users/{admin.id}", headers=_auth_header(_make_token(admin)))
    assert r.status_code == 409

    # 2) con dos admins, borrar al segundo es válido.
    second = _mk_user(tmp_db, "admin2b@example.com", "admin2b12345", "admin")
    r = client.delete(
        f"/api/users/{second.id}", headers=_auth_header(_make_token(admin)),
    )
    assert r.status_code == 204
    n = tmp_db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
    ).fetchone()["c"]
    assert n == 1


def test_delete_self(client: TestClient, admin):
    r = client.delete(f"/api/users/{admin.id}", headers=_auth_header(_make_token(admin)))
    assert r.status_code == 409


# ── POST /api/users ──────────────────────────────────────────────


def test_create_user_duplicate_email(client: TestClient, admin):
    r = client.post("/api/users", json={
        "email": "admin@example.com",
        "password": "anotherpass",
        "nombre": "Admin Original",
        "role": "empresa",
    }, headers=_auth_header(_make_token(admin)))
    assert r.status_code == 409


def test_create_user_non_admin_denied(client: TestClient, admin, agent_user):
    r = client.post("/api/users", json={
        "email": "new@example.com",
        "password": "newpass1234",
        "nombre": "Nuevo Usuario",
        "role": "empresa",
    }, headers=_auth_header(_make_token(agent_user)))
    assert r.status_code == 403


# ── Permisos DELETE ──────────────────────────────────────────────


def test_delete_user_non_admin_denied(client: TestClient, admin, agent_user):
    r = client.delete(
        f"/api/users/{admin.id}", headers=_auth_header(_make_token(agent_user)),
    )
    assert r.status_code == 403


# ── Datos ampliados (nombre, actions log) ────────────────────────


def test_create_user_persists_nombre_and_role(client: TestClient, admin, tmp_db):
    r = client.post("/api/users", json={
        "email": "maria@example.com",
        "password": "contrasena123",
        "nombre": "María Pérez",
        "role": "propietario",
    }, headers=_auth_header(_make_token(admin)))
    assert r.status_code == 201
    data = r.json()
    assert data["nombre"] == "María Pérez"
    assert data["role"] == "propietario"
    row = tmp_db.execute(
        "SELECT nombre, role FROM users WHERE email = ?", ("maria@example.com",),
    ).fetchone()
    assert row["nombre"] == "María Pérez"
    assert row["role"] == "propietario"


def test_create_user_logs_admin_action(client: TestClient, admin, tmp_db):
    r = client.post("/api/users", json={
        "email": "otro@example.com",
        "password": "contrasena123",
        "nombre": "Otro Usuario",
        "role": "empresa",
    }, headers=_auth_header(_make_token(admin)))
    assert r.status_code == 201
    row = tmp_db.execute(
        "SELECT acciones FROM users WHERE id = ?", (admin.id,),
    ).fetchone()
    import json as _json
    actions = _json.loads(row["acciones"])
    assert any(a["accion"] == "crear_usuario:otro@example.com" for a in actions)


def test_login_logs_action(client: TestClient, admin, tmp_db):
    r = client.post("/api/auth/login", json={
        "email": "admin@example.com",
        "password": "admin123456",
    })
    assert r.status_code == 200
    row = tmp_db.execute(
        "SELECT acciones FROM users WHERE id = ?", (admin.id,),
    ).fetchone()
    import json as _json
    actions = _json.loads(row["acciones"])
    assert any(a["accion"] == "login" for a in actions)


def test_user_out_includes_nombre_and_acciones(client: TestClient, admin):
    r = client.get("/api/users", headers=_auth_header(_make_token(admin)))
    assert r.status_code == 200
    data = r.json()
    assert all("nombre" in u and "acciones" in u for u in data)


def test_cannot_create_user_with_legacy_agent_role(client: TestClient, admin):
    """agent queda como legacy en BD; no se puede crear usuario nuevo con él."""
    r = client.post("/api/users", json={
        "email": "nuevo@example.com",
        "password": "contrasena123",
        "nombre": "Nuevo",
        "role": "agent",
    }, headers=_auth_header(_make_token(admin)))
    assert r.status_code == 422


def test_create_user_requires_nombre(client: TestClient, admin):
    r = client.post("/api/users", json={
        "email": "sin@nombre.com",
        "password": "contrasena123",
        "role": "empresa",
    }, headers=_auth_header(_make_token(admin)))
    assert r.status_code == 422


# ── Eliminación y tokens ─────────────────────────────────────────


def test_token_rejected_after_deletion(client: TestClient, admin, agent_user):
    token = _make_token(agent_user)
    r = client.delete(
        f"/api/users/{agent_user.id}", headers=_auth_header(_make_token(admin)),
    )
    assert r.status_code == 204
    r = client.get("/api/watchlist", headers=_auth_header(token))
    assert r.status_code == 401


def test_login_after_deletion_denied(client: TestClient, admin, agent_user):
    r = client.delete(
        f"/api/users/{agent_user.id}", headers=_auth_header(_make_token(admin)),
    )
    assert r.status_code == 204
    r = client.post("/api/auth/login", json={
        "email": "agent@example.com",
        "password": "agent123456",
    })
    assert r.status_code == 401

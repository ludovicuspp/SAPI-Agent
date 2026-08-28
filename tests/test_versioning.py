"""Tests del middleware de versionado de API (/api/v0/* → /api/*)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.deps import get_db
from scripts import auth, db


@pytest.fixture(autouse=True)
def _settings(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "test_version.db"
    db.init_db(db_file)
    monkeypatch.setenv("SAPI_DB_PATH", str(db_file))
    monkeypatch.setenv("JWT_SECRET", "test-version")
    monkeypatch.setenv("JWT_EXPIRES_MIN", "60")
    from scripts.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client(tmp_path: Path):
    db_file = tmp_path / "test_version.db"
    app = create_app()
    conn = db.connect(db_file)
    db.users_create(conn, "admin@v.local", auth.hash_password("admin1234"), role="admin")
    conn.commit()
    conn.close()

    def _override():
        c = db.connect(db_file)
        try:
            yield c
        finally:
            c.close()
    app.dependency_overrides[get_db] = _override
    return TestClient(app)


# ── V.1: /api/ sigue funcionando (compat) ─────────────────────────


def test_api_sin_version_sigue_funcionando(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── V.2: /api/v0/health funciona (alias) ─────────────────────────


def test_api_v0_health_es_alias(client):
    r = client.get("/api/v0/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── V.3: header X-API-Version en todas las respuestas ────────────


def test_api_v0_responde_con_header_version(client):
    r = client.get("/api/v0/health")
    assert r.headers.get("X-API-Version") == "v0"


def test_api_sin_version_responde_con_header_version(client):
    """Compatibilidad: también en /api/ devolvemos X-API-Version=v0."""
    r = client.get("/api/health")
    assert r.headers.get("X-API-Version") == "v0"


# ── V.4: rutas no-API no se versionan ─────────────────────────────


def test_api_v0_summary(client):
    """Verifica que un endpoint protegido también tiene alias v0."""
    r = client.get("/api/v0/summary")
    # 401 porque no hay token, pero la ruta existe (no 404)
    assert r.status_code == 401
    # Si fuera 404, el middleware habría fallado
    assert r.status_code != 404


# ── V.5: /api/v0 sin barra final también mapea ───────────────────


def test_api_v0_sin_path_alias(client):
    """Edge case: solo /api/v0 también mapea a /api (200 OK via SPA fallback)."""
    r = client.get("/api/v0")
    # /api sin path cae en el SPA fallback (index.html)
    assert r.status_code == 200
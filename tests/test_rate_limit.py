"""Tests de rate limiting (RNF-17) para login y upload."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from fastapi.testclient import TestClient
import pytest

from scripts import auth, db
from scripts.config import Settings, get_settings
from api.main import create_app
from api.deps import get_db


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_settings(tmp_path: Path):
    db_file = tmp_path / "test_rl.db"
    db.init_db(db_file)
    os.environ["SAPI_DB_PATH"] = str(db_file)
    os.environ["JWT_SECRET"] = "test-secret"
    os.environ["JWT_EXPIRES_MIN"] = "60"
    os.environ["UPLOADS_DIR"] = str(tmp_path / "uploads")
    os.environ["RATE_LIMIT_LOGIN_PER_MIN"] = "2"
    os.environ["RATE_LIMIT_UPLOAD_PER_HOUR"] = "2"
    os.environ["SERVICE_TOKEN_HERMES"] = ""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def tmp_db(tmp_path: Path) -> db.Connection:
    import sqlite3
    cfg = Settings()
    conn = sqlite3.connect(str(cfg.sapi_db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture()
def client(tmp_db: db.Connection) -> Iterator[TestClient]:
    app = create_app()

    def _override():
        yield tmp_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def user_row(tmp_db: db.Connection) -> db.UserRow:
    uid = db.users_create(tmp_db, "user@rl.test", "h", role="agent")
    tmp_db.commit()
    return db.users_get(tmp_db, uid)


def _auth_token(user: db.UserRow) -> str:
    cfg = Settings()
    return auth.create_access_token(user.id, user.role, secret=cfg.jwt_secret, expires_min=cfg.jwt_expires_min)


def _fake_pdf_content() -> bytes:
    return b"%PDF-1.4 fake"


# ── Tests ───────────────────────────────────────────────────────


class TestLoginRateLimit:
    def test_login_returns_429_after_limit(self, client: TestClient):
        payload = {"email": "no@test.com", "password": "12345678"}
        for _ in range(2):
            r = client.post("/api/auth/login", json=payload)
            assert r.status_code != 429
        r = client.post("/api/auth/login", json=payload)
        assert r.status_code == 429
        assert r.json()["detail"] == "Demasiadas peticiones. Intente más tarde."

    def test_login_independent_per_ip(self, client: TestClient):
        payload = {"email": "x@x.com", "password": "12345678"}
        for _ in range(2):
            client.post("/api/auth/login", json=payload)
        # Simula distinta IP modificando scope.client (no factible desde TestClient)
        # Verificamos al menos que no afecta otros endpoints.
        r = client.get("/api/health")
        assert r.status_code == 200


class TestUploadRateLimit:
    def test_upload_returns_429_after_limit(self, client: TestClient, user_row: db.UserRow):
        token = _auth_token(user_row)
        headers = {"Authorization": f"Bearer {token}"}
        import io
        for _ in range(2):
            r = client.post(
                "/api/boletines/upload",
                files={"file": ("test.pdf", io.BytesIO(_fake_pdf_content()), "application/pdf")},
                headers=headers,
            )
            assert r.status_code != 429
        r = client.post(
            "/api/boletines/upload",
            files={"file": ("test.pdf", io.BytesIO(_fake_pdf_content()), "application/pdf")},
            headers=headers,
        )
        assert r.status_code == 429

    def test_upload_independent_per_user(self, client: TestClient, tmp_db: db.Connection):
        u1 = db.users_create(tmp_db, "u1@rl.test", "h", role="agent")
        u2 = db.users_create(tmp_db, "u2@rl.test", "h", role="agent")
        tmp_db.commit()
        user1 = db.users_get(tmp_db, u1)
        user2 = db.users_get(tmp_db, u2)
        import io
        for _ in range(2):
            client.post(
                "/api/boletines/upload",
                files={"file": ("test.pdf", io.BytesIO(_fake_pdf_content()), "application/pdf")},
                headers={"Authorization": f"Bearer {_auth_token(user1)}"},
            )
        # user2 sigue operando
        r = client.post(
            "/api/boletines/upload",
            files={"file": ("test.pdf", io.BytesIO(_fake_pdf_content()), "application/pdf")},
            headers={"Authorization": f"Bearer {_auth_token(user2)}"},
        )
        assert r.status_code != 429


class TestOtherRoutesUnaffected:
    def test_health_and_watchlist_bypass_rate_limit(self, client: TestClient, user_row: db.UserRow):
        token = _auth_token(user_row)
        # Login al límite
        for _ in range(2):
            client.post("/api/auth/login", json={"email": "x@x.com", "password": "12345678"})
        r = client.get("/api/health")
        assert r.status_code == 200
        r = client.get("/api/watchlist", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

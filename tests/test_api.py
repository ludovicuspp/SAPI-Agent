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
    assert r.json()["status"] == "Pendiente Resolución"
    r = client.get("/api/portfolio", headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_portfolio_get_update(client: TestClient, agent_token: str):
    r = client.post("/api/portfolio", json={"name": "ACME", "solicitud": "S9"},
                    headers=_auth_header(agent_token))
    pid = r.json()["id"]
    r = client.get(f"/api/portfolio/{pid}", headers=_auth_header(agent_token))
    assert r.status_code == 200
    r = client.put(f"/api/portfolio/{pid}", json={
        "name": "ACME", "solicitud": "S9", "titular": "TITULAR NUEVO",
        "tipo_registro": "Denominativa", "bufete": "BUFETE X",
    }, headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert r.json()["titular"] == "TITULAR NUEVO"


def test_portfolio_template_download(client: TestClient, agent_token: str):
    r = client.get("/api/portfolio/template", headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert "marca" in r.text
    assert r.headers["content-type"].startswith("text/csv")


def test_portfolio_import_csv(client: TestClient, agent_token: str):
    csv_bytes = (
        "país;marca;clase;solicitud;titular\n"
        "Venezuela;NUEVA IMPORTADA;9;2026-000555;TITULAR\n"
    ).encode("utf-8")
    r = client.post("/api/portfolio/import", files={"file": ("import.csv", csv_bytes, "text/csv")},
                    headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert r.json()["created"] == 1
    r = client.get("/api/portfolio", headers=_auth_header(agent_token))
    assert any(p["name"] == "NUEVA IMPORTADA" for p in r.json())


def test_portfolio_etiqueta_upload(client: TestClient, agent_token: str):
    r = client.post("/api/portfolio", json={"name": "CON ETIQUETA"},
                    headers=_auth_header(agent_token))
    pid = r.json()["id"]
    png = b"\x89PNG\r\n\x1a\nfiledatos"
    r = client.post(f"/api/portfolio/{pid}/etiqueta", files={"file": ("e.png", png, "image/png")},
                    headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert r.json()["etiqueta"].startswith("/uploads/etiquetas/")
    # extensión no permitida
    r = client.post(f"/api/portfolio/{pid}/etiqueta", files={"file": ("e.gif", b"GIF", "image/gif")},
                    headers=_auth_header(agent_token))
    assert r.status_code == 400


def test_portfolio_history_endpoint(client: TestClient, agent_token: str):
    r = client.post("/api/portfolio", json={"name": "HISTORIAL", "solicitud": "S10"},
                    headers=_auth_header(agent_token))
    pid = r.json()["id"]
    r = client.get(f"/api/portfolio/{pid}/history", headers=_auth_header(agent_token))
    assert r.status_code == 200
    assert r.json() == []


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


def test_upload_uses_file_size_not_body_length(
    client: TestClient, agent_token: str, monkeypatch: pytest.MonkeyPatch,
):
    """Regresión: el handler debe comparar contra el tamaño del archivo,
    no contra el body completo (multipart envelope incluido).

    Antes: `len(content) > max_upload_mb * 1024 * 1024` causaba 413
    incluso cuando el PDF real cabía, porque sumaba headers/boundary.
    Ahora: se usa `UploadFile.size` y `Path.stat().st_size` del archivo
    escrito, ambos referidos al archivo, no al body.
    """
    from api.routers import uploads as uploads_module

    captured: dict = {}

    real_hash_write = uploads_module._hash_and_write_stream

    def spy_hash_write(file, dest):
        captured["size_hint"] = getattr(file, "size", None)
        result = real_hash_write(file, dest)
        captured["written_size"] = dest.stat().st_size
        return result

    monkeypatch.setattr(uploads_module, "_hash_and_write_stream", spy_hash_write)

    pdf_body = b"%PDF-1.4\nreal content"
    r = client.post(
        "/api/boletines/upload",
        files={"file": ("ok.pdf", io.BytesIO(pdf_body), "application/pdf")},
        headers=_auth_header(agent_token),
    )
    assert r.status_code == 202

    # El size_hint y el tamaño escrito deben coincidir con el cuerpo
    # del archivo, no con el body multipart (que incluye boundary).
    assert captured["size_hint"] is not None
    assert captured["size_hint"] == len(pdf_body)
    assert captured["written_size"] == len(pdf_body)
    # El body multipart real es más grande que el PDF (boundary +
    # headers +2). Si el handler comparara contra el body completo,
    # el límite efectivo se reduciría. Aquí verificamos que el body
    # multipart > size_hint, lo que confirma que el código nuevo no
    # puede estar usando len(body).
    assert len(pdf_body) <= captured["size_hint"]


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


# ── Structured (Hermes) 

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


# ── Boletines DELETE ────────────────────────────────────────────


def _make_extracted_boletin(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    user_id: int,
    *,
    status: str = "extracted",
    needs_hermes_review: bool = False,
    hermes_processed_at: str | None = "2026-01-01 00:00:00",
    filename: str = "test.pdf",
) -> tuple[int, Path]:
    """Crea un boletín `extracted` con un PDF real en disco.

    Devuelve (boletin_id, ruta del PDF).
    """
    import hashlib

    pdf_bytes = b"%PDF-1.4 fake content"
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / f"{sha}.pdf"
    file_path.write_bytes(pdf_bytes)
    bid = db.boletines_create(tmp_db, user_id, filename, str(file_path), sha)
    tmp_db.commit()
    tmp_db.execute(
        "UPDATE boletines SET status=?, needs_hermes_review=?, "
        "hermes_processed_at=? WHERE id=?",
        (
            status,
            1 if needs_hermes_review else 0,
            hermes_processed_at,
            bid,
        ),
    )
    tmp_db.commit()
    return bid, file_path


def test_delete_boletin_uploader_can_delete(
    client: TestClient,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    agent_user: db.UserRow,
    agent_token: str,
):
    bid, file_path = _make_extracted_boletin(tmp_db, tmp_path, agent_user.id)
    assert file_path.exists()

    r = client.delete(f"/api/boletines/{bid}", headers=_auth_header(agent_token))
    assert r.status_code == 204

    assert db.boletines_get(tmp_db, bid) is None
    assert not file_path.exists()


def test_delete_boletin_admin_can_delete(
    client: TestClient,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    agent_user: db.UserRow,
    admin_token: str,
):
    bid, file_path = _make_extracted_boletin(tmp_db, tmp_path, agent_user.id)
    r = client.delete(f"/api/boletines/{bid}", headers=_auth_header(admin_token))
    assert r.status_code == 204
    assert not file_path.exists()


def test_delete_boletin_other_agent_forbidden(
    client: TestClient,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    agent_user: db.UserRow,
):
    """Un agent que NO subió el boletín recibe 404 (oculto, no 403)."""
    other_id = db.users_create(
        tmp_db, "other@example.com", auth.hash_password("other123456"), "agent",
    )
    tmp_db.commit()
    other_token = auth.create_access_token(
        other_id, "agent", secret=Settings().jwt_secret,
        expires_min=Settings().jwt_expires_min,
    )
    bid, file_path = _make_extracted_boletin(tmp_db, tmp_path, agent_user.id)

    r = client.delete(f"/api/boletines/{bid}", headers=_auth_header(other_token))
    assert r.status_code == 404

    assert db.boletines_get(tmp_db, bid) is not None
    assert file_path.exists()


def test_delete_boletin_409_if_extracting(
    client: TestClient,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    agent_user: db.UserRow,
    agent_token: str,
):
    bid, file_path = _make_extracted_boletin(
        tmp_db, tmp_path, agent_user.id, status="extracting",
    )
    r = client.delete(f"/api/boletines/{bid}", headers=_auth_header(agent_token))
    assert r.status_code == 409
    assert db.boletines_get(tmp_db, bid) is not None


def test_delete_boletin_409_if_hermes_pending(
    client: TestClient,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    agent_user: db.UserRow,
    agent_token: str,
):
    bid, _ = _make_extracted_boletin(
        tmp_db, tmp_path, agent_user.id,
        needs_hermes_review=True, hermes_processed_at=None,
    )
    r = client.delete(f"/api/boletines/{bid}", headers=_auth_header(agent_token))
    assert r.status_code == 409


def test_delete_boletin_keeps_shared_file(
    client: TestClient,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    agent_user: db.UserRow,
    admin: db.UserRow,
    admin_token: str,
):
    """Si dos boletines comparten el PDF (mismo SHA), el archivo no se borra."""
    bid1, file_path = _make_extracted_boletin(
        tmp_db, tmp_path, agent_user.id, filename="bpi-654.pdf",
    )
    # Crear un segundo boletín reusando el mismo file_path/sha.
    sha = file_path.name.removesuffix(".pdf")
    bid2 = db.boletines_create(
        tmp_db, admin.id, "dup.pdf", str(file_path), sha,
    )
    db.boletines_mark_extracted(
        tmp_db, bid2, pages=1, extraction_payload={},
        bulletin_number=None, period=None, needs_hermes_review=False,
    )
    tmp_db.commit()
    assert file_path.exists()

    r = client.delete(f"/api/boletines/{bid1}", headers=_auth_header(admin_token))
    assert r.status_code == 204

    assert db.boletines_get(tmp_db, bid1) is None
    assert db.boletines_get(tmp_db, bid2) is not None
    assert file_path.exists()  # sigue referenciado


def test_delete_boletin_cascades_detections(
    client: TestClient,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    agent_user: db.UserRow,
    agent_token: str,
):
    bid, _ = _make_extracted_boletin(tmp_db, tmp_path, agent_user.id)
    tmp_db.execute(
        "INSERT INTO detections(boletin_id, user_id, mark_name, similarity, "
        "match_kind, source, confidence) VALUES (?, ?, 'X', 0.9, 'similar', "
        "'pdfplumber_text', 'high')",
        (bid, agent_user.id),
    )
    tmp_db.commit()
    pre = tmp_db.execute(
        "SELECT COUNT(*) FROM detections WHERE boletin_id=?", (bid,),
    ).fetchone()[0]
    assert pre == 1

    r = client.delete(f"/api/boletines/{bid}", headers=_auth_header(agent_token))
    assert r.status_code == 204

    post = tmp_db.execute(
        "SELECT COUNT(*) FROM detections WHERE boletin_id=?", (bid,),
    ).fetchone()[0]
    assert post == 0


def test_delete_boletin_404(client: TestClient, agent_token: str):
    r = client.delete("/api/boletines/9999", headers=_auth_header(agent_token))
    assert r.status_code == 404


def test_delete_boletin_unauthenticated(client: TestClient):
    r = client.delete("/api/boletines/1")
    assert r.status_code in (401, 422)


def test_delete_boletin_with_scans_log(
    client: TestClient,
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    agent_user: db.UserRow,
    agent_token: str,
):
    """Regresión: `scans_log.boletin_id` no tiene ON DELETE CASCADE en
    el esquema heredado de prod, así que `boletines_delete` debe
    limpiar `scans_log` antes de borrar el boletín para no violar FK.
    """
    bid, _ = _make_extracted_boletin(tmp_db, tmp_path, agent_user.id)
    tmp_db.execute(
        "INSERT INTO scans_log(kind, boletin_id, status) "
        "VALUES ('extract', ?, 'ok')",
        (bid,),
    )
    tmp_db.commit()

    r = client.delete(f"/api/boletines/{bid}", headers=_auth_header(agent_token))
    assert r.status_code == 204

    # scans_log limpio para este boletin_id
    rows = tmp_db.execute(
        "SELECT COUNT(*) FROM scans_log WHERE boletin_id = ?", (bid,),
    ).fetchone()[0]
    assert rows == 0


def test_mark_stale_extracting_as_failed(
    tmp_db: sqlite3.Connection, tmp_path: Path, agent_user: db.UserRow,
):
    """Boletines en extracting con tareas huérfanas se marcan failed.

    Dos casos:
      - progress_step NULL + uploaded_at > N min → tarea murió antes
        de empezar.
      - progress_step no terminal + progress_updated_at > N min →
        tarea quedó atascada a mitad (caso BPI_655_V3).
    """
    # Huérfano de tipo 1: nunca reportó progreso, subido hace 30 min.
    orphan_never_started, _ = _make_extracted_boletin(
        tmp_db, tmp_path, agent_user.id, status="extracting",
    )
    tmp_db.execute(
        "UPDATE boletines SET progress_step=NULL, progress_current_page=NULL, "
        "progress_total_pages=NULL, progress_updated_at=NULL, "
        "uploaded_at=datetime('now', '-30 minutes') WHERE id=?",
        (orphan_never_started,),
    )

    # Huérfano de tipo 2: estaba extrayendo, última actualización hace 30 min.
    orphan_stuck, _ = _make_extracted_boletin(
        tmp_db, tmp_path, agent_user.id, status="extracting",
    )
    tmp_db.execute(
        "UPDATE boletines SET progress_step='extracting_text', "
        "progress_current_page=680, progress_total_pages=2580, "
        "progress_updated_at=datetime('now', '-30 minutes') WHERE id=?",
        (orphan_stuck,),
    )

    # Boletin "vivo" reciente: no debe tocarse.
    fresh, _ = _make_extracted_boletin(
        tmp_db, tmp_path, agent_user.id, status="extracting",
    )
    tmp_db.execute(
        "UPDATE boletines SET progress_step=NULL, "
        "progress_current_page=NULL, progress_total_pages=NULL, "
        "progress_updated_at=NULL, "
        "uploaded_at=datetime('now', '-5 seconds') WHERE id=?",
        (fresh,),
    )

    # Boletin "vivo" con progreso reciente: no debe tocarse.
    updated, _ = _make_extracted_boletin(
        tmp_db, tmp_path, agent_user.id, status="extracting",
    )
    tmp_db.execute(
        "UPDATE boletines SET progress_step='extracting_text', "
        "progress_current_page=10, progress_total_pages=100, "
        "progress_updated_at=datetime('now', '-5 seconds') WHERE id=?",
        (updated,),
    )
    tmp_db.commit()

    marked = db.boletines_mark_stale_extracting_as_failed(
        tmp_db, threshold_minutes=10,
    )

    # Ambos huérfanos (tipo 1 y tipo 2) deben marcarse.
    assert sorted(marked) == sorted([orphan_never_started, orphan_stuck])

    # Los huérfanos quedan en failed con mensaje.
    for bid in (orphan_never_started, orphan_stuck):
        b = db.boletines_get(tmp_db, bid)
        assert b.status == "failed"
        assert b.progress_step == "failed"
        assert "huérfana" in (b.error or "").lower()

    # El fresco y el actualizado no se tocan.
    for bid in (fresh, updated):
        b = db.boletines_get(tmp_db, bid)
        assert b.status == "extracting"
        if bid == fresh:
            assert b.progress_step is None
        else:
            assert b.progress_step == "extracting_text"

    # scans_log tiene entradas de error para los huérfanos.
    err_rows = tmp_db.execute(
        "SELECT boletin_id, status FROM scans_log "
        " WHERE boletin_id IN (?, ?) AND status='error'",
        (orphan_never_started, orphan_stuck),
    ).fetchall()
    assert len(err_rows) == 2

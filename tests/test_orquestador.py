"""Tests de la conexión con el Orquestador (Hermes sapi-monitor).

Cubre:
- B1.1: endpoint /api/boletines/{id}/structured con token correcto
- B1.2: token vacío -> 503
- B1.3: token incorrecto -> 403
- B1.4: pending_boletines.py lista correctamente
- B1.5: watchdog.sh imprime SIN_PENDIENTES cuando no hay nada
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.deps import get_db
from scripts import db, auth


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _settings(tmp_path: Path, monkeypatch):
    """Configura Settings para tests: BD temporal + JWT secret + token Hermes."""
    db_file = tmp_path / "test.db"
    db.init_db(db_file)
    monkeypatch.setenv("SAPI_DB_PATH", str(db_file))
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("JWT_EXPIRES_MIN", "60")
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("SERVICE_TOKEN_HERMES", "hermes-test-token")
    from scripts.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client(tmp_path: Path):
    """TestClient con BD temporal y admin seedeado."""
    db_file = tmp_path / "test.db"
    app = create_app()
    conn = db.connect(db_file)
    db.init_db(db_file)
    # Crear admin
    admin_id = db.users_create(conn, "admin@test.local", auth.hash_password("admin1234"), role="admin")
    conn.commit()
    # Override de get_db
    def _override_get_db():
        c = db.connect(db_file)
        try:
            yield c
        finally:
            c.close()
    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)


@pytest.fixture()
def boletin_row(tmp_path: Path):
    """Crea un boletin en BD para los tests del endpoint."""
    db_file = tmp_path / "test.db"
    conn = db.connect(db_file)
    admin_id = conn.execute("SELECT id FROM users WHERE email='admin@test.local'").fetchone()[0]
    sha = "deadbeef" * 8
    bid = db.boletines_create(conn, admin_id, "BPI-654.pdf", str(tmp_path / "BPI-654.pdf"), sha)
    conn.commit()
    conn.close()
    return bid


# ── B1.1: endpoint con token correcto ─────────────────────────────


def test_orq_structured_token_correcto(client, boletin_row):
    """Token X-Hermes-Token correcto -> 200 (processed)."""
    payload = {
        "boletin_id": boletin_row,
        "entries": [
            {
                "expediente": "2024-000001",
                "marca": "ACME TEST",
                "clase_niza": 25,
                "titular": "ACME HOLDINGS LLC",
                "estatus": "PUBLICADA",
                "pagina": 1,
                "fuente": "hermes_vision",
                "confianza": "high",
            }
        ],
    }
    r = client.post(
        f"/api/boletines/{boletin_row}/structured",
        json=payload,
        headers={"X-Hermes-Token": "hermes-test-token"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "processed"


# ── B1.2: token vacío -> 503 (SERVICE_TOKEN_HERMES no configurado)


def test_orq_structured_sin_token_configurado(tmp_path: Path, monkeypatch):
    """Si SERVICE_TOKEN_HERMES está vacío en el .env, requiere_hermes devuelve 503."""
    monkeypatch.setenv("SERVICE_TOKEN_HERMES", "")
    from scripts.config import get_settings
    get_settings.cache_clear()

    db_file = tmp_path / "test.db"
    app = create_app()
    conn = db.connect(db_file)
    db.init_db(db_file)
    admin_id = db.users_create(conn, "admin@test.local", auth.hash_password("admin1234"), role="admin")
    sha = "deadbeef" * 8
    bid = db.boletines_create(conn, admin_id, "B.pdf", str(tmp_path / "B.pdf"), sha)
    conn.commit()
    conn.close()

    def _override_get_db():
        c = db.connect(db_file)
        try:
            yield c
        finally:
            c.close()
    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)
    payload = {"boletin_id": bid, "entries": [{"expediente": "X", "marca": "Y", "clase_niza": 25, "titular": "Z", "estatus": "PUBLICADA"}]}
    r = c.post(
        f"/api/boletines/{bid}/structured",
        json=payload,
        headers={"X-Hermes-Token": "cualquiera"},
    )
    assert r.status_code == 503


# ── B1.3: token incorrecto -> 403


def test_orq_structured_token_incorrecto(client, boletin_row):
    payload = {"boletin_id": boletin_row, "entries": [{"expediente": "X", "marca": "Y", "clase_niza": 25, "titular": "Z", "estatus": "PUBLICADA"}]}
    r = client.post(
        f"/api/boletines/{boletin_row}/structured",
        json=payload,
        headers={"X-Hermes-Token": "token-equivocado"},
    )
    assert r.status_code == 403


# ── B1.4: pending_boletines.py lista correctamente


def test_orq_pending_boletines_script(tmp_path: Path, monkeypatch):
    """pending_boletines.py lista boletines con needs_hermes_review=1 sin procesar."""
    db_file = tmp_path / "test.db"
    db.init_db(db_file)
    conn = db.connect(db_file)
    admin_id = db.users_create(conn, "admin@test.local", "x", role="admin")
    sha = "a" * 64
    bid = db.boletines_create(conn, admin_id, "P.pdf", str(tmp_path / "P.pdf"), sha)
    db.boletines_mark_extracted(
        conn, boletin_id=bid, pages=2,
        extraction_payload={"pages": [{"page_number": 1, "text": "x", "char_count": 1, "has_images": True, "low_confidence": False}]},
        bulletin_number=999, period=None,
        needs_hermes_review=True, entries_matcheables=0, entries_hermes_pending=1,
    )
    conn.commit()
    conn.close()

    script = Path(__file__).resolve().parent.parent / "hermes" / "skills" / "sapi-monitor" / "scripts" / "pending_boletines.py"
    r = subprocess.run(
        [sys.executable, str(script), "--db", str(db_file), "--json"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert len(data) == 1
    assert data[0]["boletin_id"] == bid
    assert data[0]["pages_with_images"] >= 1


# ── B1.5: watchdog.sh SIN_PENDIENTES cuando no hay nada


def test_orq_watchdog_sin_pendientes(tmp_path: Path):
    """watchdog.sh imprime 'SIN_PENDIENTES' si no hay boletines pendientes."""
    repo_real = Path(__file__).resolve().parent.parent  # repo real con hermes/
    fake_data = tmp_path / "fake_repo" / "data"
    fake_data.mkdir(parents=True)
    db_file = fake_data / "sapi.db"
    db.init_db(db_file)
    # BD vacía de boletines: init_db ya creó el esquema

    script = repo_real / "hermes" / "skills" / "sapi-monitor" / "watchdog.sh"
    # Pasamos el repo REAL (para que encuentre hermes/), pero con DB vacía
    # mediante SAPI_REPO_DIR=tmp_path/fake_repo no funciona porque no tiene hermes/.
    # Solución: crear symlink del hermes/ del repo real al fake.
    fake_repo = tmp_path / "fake_repo"
    if not (fake_repo / "hermes").exists():
        (fake_repo / "hermes").symlink_to(repo_real / "hermes")

    r = subprocess.run(
        ["bash", str(script), str(fake_repo)],
        capture_output=True, text=True, timeout=10,
    )
    assert r.stdout.strip() == "SIN_PENDIENTES", f"stdout={r.stdout!r}, stderr={r.stderr!r}"


# ── B1.6: defensa contra duplicados (hermes_processed_at)


def test_orq_structured_idempotente(client, boletin_row):
    """Segundo POST al mismo boletin devuelve 'already_processed'."""
    payload = {
        "boletin_id": boletin_row,
        "entries": [{
            "expediente": "2024-000001",
            "marca": "ACME",
            "clase_niza": 25,
            "titular": "ACME LLC",
            "estatus": "PUBLICADA",
        }],
    }
    headers = {"X-Hermes-Token": "hermes-test-token"}

    # Primer POST: processed
    r1 = client.post(f"/api/boletines/{boletin_row}/structured", json=payload, headers=headers)
    assert r1.status_code == 200
    assert r1.json()["status"] == "processed"

    # Segundo POST: already_processed
    r2 = client.post(f"/api/boletines/{boletin_row}/structured", json=payload, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_processed"
    assert r2.json()["entries_added"] == 0


# ── B1.7: cap top-5 matches por entry


def test_orq_structured_cap_top5(client, boletin_row, tmp_path: Path):
    """Una entry con muchas watchlists solo genera 5 detections (las mejores)."""
    db_file = tmp_path / "test.db"
    conn = db.connect(db_file)
    admin_id = conn.execute("SELECT id FROM users WHERE email='admin@test.local'").fetchone()[0]
    # Crear 10 watchlists muy parecidas a "ACME" (todas deben matchear)
    for i in range(10):
        db.watchlist_add(conn, admin_id, f"ACME VAR {i}", class_nice=None, notes=None)
    conn.commit()
    conn.close()

    payload = {
        "boletin_id": boletin_row,
        "entries": [{
            "expediente": "2024-000001",
            "marca": "ACME",
            "clase_niza": 25,
            "titular": "ACME",
            "estatus": "PUBLICADA",
        }],
    }
    r = client.post(
        f"/api/boletines/{boletin_row}/structured",
        json=payload,
        headers={"X-Hermes-Token": "hermes-test-token"},
    )
    assert r.status_code == 200
    assert r.json()["entries_added"] == 5  # cap top-5


# ── B1.8: reverify detection con Hermes (defensa falsos positivos) ──


def test_orq_reverify_detection_needs_hermes(client, boletin_row, tmp_path: Path):
    """POST /api/detections/{id}/reverify marca needs_hermes_reverify=1
    y resetea hermes_processed_at del boletín asociado."""
    db_file = tmp_path / "test.db"
    conn = db.connect(db_file)

    # Marcar boletin como needs_hermes_review=1
    conn.execute(
        "UPDATE boletines SET needs_hermes_review = 1 WHERE id = ?",
        (boletin_row,),
    )
    # Crear una detection
    admin_id = conn.execute("SELECT id FROM users WHERE email='admin@test.local'").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO detections(boletin_id, user_id, mark_name, similarity, "
        "match_kind, source, confidence) VALUES (?,?,?,?,?,?,?)",
        (boletin_row, admin_id, "TEST", 0.9, "similar",
         "pdfplumber_text", "high"),
    )
    detection_id = cur.lastrowid
    # Marcar hermes_processed_at para verificar que se resetea
    conn.execute(
        "UPDATE boletines SET hermes_processed_at = datetime('now') WHERE id = ?",
        (boletin_row,),
    )
    conn.commit()
    conn.close()

    # Necesitamos token de admin
    from scripts.auth import create_access_token
    from scripts.config import get_settings
    token = create_access_token(
        admin_id, "admin",
        secret=get_settings().jwt_secret,
        expires_min=60,
    )
    r = client.post(
        f"/api/detections/{detection_id}/reverify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["needs_hermes_reverify"] is True

    # Verificar que hermes_processed_at del boletín fue reseteada
    conn = db.connect(db_file)
    bol = db.boletines_get(conn, boletin_row)
    assert bol.hermes_processed_at is None
    conn.close()


def test_orq_reverify_detection_sin_needs_hermes_rechaza(client, boletin_row, tmp_path: Path):
    """Si el boletín no requiere Hermes, el reverify devuelve 400."""
    db_file = tmp_path / "test.db"
    conn = db.connect(db_file)
    admin_id = conn.execute("SELECT id FROM users WHERE email='admin@test.local'").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO detections(boletin_id, user_id, mark_name, similarity, "
        "match_kind, source, confidence) VALUES (?,?,?,?,?,?,?)",
        (boletin_row, admin_id, "X", 0.9, "similar", "pdfplumber_text", "high"),
    )
    detection_id = cur.lastrowid
    conn.commit()
    conn.close()

    from scripts.auth import create_access_token
    from scripts.config import get_settings
    token = create_access_token(
        admin_id, "admin",
        secret=get_settings().jwt_secret,
        expires_min=60,
    )
    r = client.post(
        f"/api/detections/{detection_id}/reverify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400

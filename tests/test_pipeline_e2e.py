"""Test E2E del pipeline con un boletín REAL SAPI.

Extrae las primeras 5 páginas del PDF real 'BPI 654 listo.pdf'
(1844 páginas, 1358 con imágenes) a un PDF temporal pequeño para
validar el pipeline completo:
  PDF → extracción pdfplumber → parsers → DB → matchings → detections

Si 'needs_hermes_review=1', simula la llamada de Hermes Vision
(endpoint /api/boletines/{id}/structured) y verifica que
hermes_processed_at se setea.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.deps import get_db
from scripts import auth, db
from scripts.orchestration import processor


ORIGINAL_PDF = Path("/home/luisv/SAPI-Agent/data/uploads/BPI 654 listo.pdf")


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _settings(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "test_e2e.db"
    db.init_db(db_file)
    monkeypatch.setenv("SAPI_DB_PATH", str(db_file))
    monkeypatch.setenv("JWT_SECRET", "test-secret-e2e")
    monkeypatch.setenv("JWT_EXPIRES_MIN", "60")
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("SERVICE_TOKEN_HERMES", "hermes-test-e2e")
    from scripts.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def small_pdf(tmp_path: Path):
    """Extrae las primeras 5 páginas del PDF real a un archivo pequeño.

    Si el PDF original no existe (entornos donde data/uploads/ no
    está disponible), skipea el test.
    """
    if not ORIGINAL_PDF.exists():
        pytest.skip(f"Boletín real no disponible: {ORIGINAL_PDF}")

    out = tmp_path / "bpi654_first5.pdf"
    try:
        import pymupdf as fitz  # type: ignore
    except ImportError:
        try:
            import fitz  # type: ignore
        except ImportError:
            pytest.skip("pymupdf no instalado")

    src = fitz.open(str(ORIGINAL_PDF))
    dst = fitz.open()
    n = min(5, src.page_count)
    for i in range(n):
        dst.insert_pdf(src, from_page=i, to_page=i)
    dst.save(str(out))
    src.close()
    dst.close()
    return out


@pytest.fixture()
def db_file(tmp_path: Path):
    return tmp_path / "test_e2e.db"


# ── E2E.1: extracción + parsers funcionan ──────────────────────────


def test_e2e_pdf_real_extraccion_basica(small_pdf, db_file):
    """Procesa las primeras 5 páginas del BPI 654 real."""
    conn = db.connect(db_file)
    user_id = db.users_create(conn, "e2e@test.local", auth.hash_password("e2e1234"), role="agent")
    conn.commit()

    result = processor.process_pdf(small_pdf, user_id=user_id, conn=conn, notify=False)

    assert result is not None
    assert result.filename == small_pdf.name
    assert result.pages_extracted >= 1
    assert result.pages_extracted <= 5
    assert result.entries_parsed >= 0


# ── E2E.2: estado de la BD tras procesar ─────────────────────────


def test_e2e_db_estado_despues_de_procesar(small_pdf, db_file):
    conn = db.connect(db_file)
    user_id = db.users_create(conn, "e2e@test.local", auth.hash_password("e2e1234"), role="agent")
    conn.commit()

    result = processor.process_pdf(small_pdf, user_id=user_id, conn=conn, notify=False)
    conn.commit()

    bol = db.boletines_get(conn, result.boletin_id)
    assert bol is not None
    assert bol.status == "extracted"
    assert bol.extraction_json


# ── E2E.3: si needs_hermes_review, simular Hermes Vision ─────────


def test_e2e_hermes_vision_si_necesario(small_pdf, db_file):
    conn = db.connect(db_file)
    user_id = db.users_create(conn, "e2e@test.local", auth.hash_password("e2e1234"), role="agent")
    db.watchlist_add(conn, user_id, "ACME", class_nice=25, notes="test e2e")
    conn.commit()

    result = processor.process_pdf(small_pdf, user_id=user_id, conn=conn, notify=False)
    conn.commit()

    bol = db.boletines_get(conn, result.boletin_id)
    assert bol is not None

    if not bol.needs_hermes_review:
        pytest.skip("Las primeras 5 páginas no requieren Hermes Vision")

    # Simular POST de Hermes Vision
    app = create_app()
    def _override_get_db():
        c = db.connect(db_file)
        try:
            yield c
        finally:
            c.close()
    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)

    payload = {
        "boletin_id": result.boletin_id,
        "entries": [{
            "expediente": "2024-654001",
            "marca": "ACME TEST",
            "clase_niza": 25,
            "titular": "ACME HOLDINGS",
            "pais": "VENEZUELA",
            "estatus": "PUBLICADA",
            "pagina": 1,
            "fuente": "hermes_vision",
            "confianza": "high",
        }],
    }
    r = c.post(
        f"/api/boletines/{result.boletin_id}/structured",
        json=payload,
        headers={"X-Hermes-Token": "hermes-test-e2e"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "processed"

    bol2 = db.boletines_get(conn, result.boletin_id)
    assert bol2.hermes_processed_at is not None

    detections = conn.execute(
        "SELECT * FROM detections WHERE boletin_id=?", (result.boletin_id,)
    ).fetchall()
    assert len(detections) >= 1
    assert detections[0]["mark_name"] == "ACME TEST"
    assert detections[0]["source"] == "hermes_vision"


# ── E2E.4: pipeline falla gracefully con PDF corrupto ─────────────


def test_e2e_pdf_corrupto_no_crashea(db_file):
    """Si el PDF está corrupto, processor.process_pdf debe manejar la excepción."""
    conn = db.connect(db_file)
    user_id = db.users_create(conn, "e2e@test.local", auth.hash_password("e2e1234"), role="agent")
    conn.commit()

    bad_pdf = db_file.parent / "bad.pdf"
    bad_pdf.write_bytes(b"not a real pdf")

    with pytest.raises(Exception):
        # Debe lanzar (el caller / endpoint debe marcar como failed)
        processor.process_pdf(bad_pdf, user_id=user_id, conn=conn, notify=False)


# ── E2E.5: idempotencia — procesar dos veces el mismo boletin ────


def test_e2e_idempotencia(small_pdf, db_file):
    """Procesar el mismo boletin dos veces (mismo SHA) genera 2 filas distintas
    porque cada process_pdf crea su propia fila. Lo que validamos es que
    el SHA es estable y los extraction_json son idénticos para el mismo PDF."""
    conn = db.connect(db_file)
    user_id = db.users_create(conn, "e2e@test.local", auth.hash_password("e2e1234"), role="agent")
    conn.commit()

    r1 = processor.process_pdf(small_pdf, user_id=user_id, conn=conn, notify=False)
    conn.commit()
    bol1 = db.boletines_get(conn, r1.boletin_id)

    r2 = processor.process_pdf(small_pdf, user_id=user_id, conn=conn, notify=False)
    conn.commit()
    bol2 = db.boletines_get(conn, r2.boletin_id)

    # Mismo SHA (mismo PDF)
    assert bol1.file_sha256 == bol2.file_sha256
    # Extracciones idénticas
    assert bol1.extraction_json == bol2.extraction_json

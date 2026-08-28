"""Regression test del bug: upload NO debe duplicar filas en BD.

Antes del fix, ``processor.process_pdf`` creaba su propia fila,
resultando en 2 filas por upload (la del endpoint quedaba huérfana
en 'extracting' para siempre).
"""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.deps import get_db
from scripts import auth, db


@pytest.fixture(autouse=True)
def _settings(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "test_upload_nodup.db"
    db.init_db(db_file)
    monkeypatch.setenv("SAPI_DB_PATH", str(db_file))
    monkeypatch.setenv("JWT_SECRET", "test-nodup")
    monkeypatch.setenv("JWT_EXPIRES_MIN", "60")
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("SERVICE_TOKEN_HERMES", "")
    from scripts.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_upload_no_duplica_fila(tmp_path: Path):
    db_file = tmp_path / "test_upload_nodup.db"
    app = create_app()

    conn = db.connect(db_file)
    admin_id = db.users_create(
        conn, "admin@nodup.local", auth.hash_password("admin1234"), role="admin",
    )
    conn.commit()
    conn.close()

    def _override():
        c = db.connect(db_file)
        try:
            yield c
        finally:
            c.close()
    app.dependency_overrides[get_db] = _override
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
    conn = db.connect(db_file)
    bol = db.boletines_get(conn, bid)
    conn.close()
    _process_boletin_task(bid, bol.file_path, admin_id)

    # Solo debe haber UNA fila con ese SHA, y su estado debe ser 'extracted' o 'failed'
    conn = db.connect(db_file)
    rows = conn.execute(
        "SELECT id, status FROM boletines WHERE file_sha256=?",
        (bol.file_sha256,),
    ).fetchall()
    assert len(rows) == 1, f"Esperaba 1 fila, encontré {len(rows)}: {rows}"
    assert rows[0]["id"] == bid
    assert rows[0]["status"] in ("extracted", "failed")
    conn.close()
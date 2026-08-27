"""Fixtures de la skill sapi-monitor: BD temporal read-only."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts import db


@pytest.fixture()
def tmp_db_path(tmp_path: Path) -> Path:
    """Crea una BD SAPI temporal completa en disco y devuelve su ruta."""
    db_file = tmp_path / "test_sapi.db"
    db.init_db(db_file)
    return db_file


@pytest.fixture()
def tmp_db(tmp_db_path: Path) -> sqlite3.Connection:
    """Conexión de escritura para sembrar datos en la BD temporal."""
    conn = db.connect(tmp_db_path)
    yield conn
    conn.close()


def make_boletin(
    conn: sqlite3.Connection,
    *,
    user_id: int | None = None,
    filename: str = "BPI_999.pdf",
    needs_hermes: int = 1,
    status: str = "extracted",
    hermes_processed_at: str | None = None,
    pages: int = 2,
) -> int:
    """Crea una fila en ``boletines`` con un ``extraction_json`` de ejemplo.

    Return el boletin_id creado.
    """
    import io
    import hashlib

    if user_id is None:
        # Crear un usuario agente si no existe (FK de boletines).
        existing = conn.execute(
            "SELECT id FROM users WHERE email = 'agent@test.local'"
        ).fetchone()
        if existing:
            user_id = existing["id"]
        else:
            user_id = db.users_create(
                conn, "agent@test.local", "hash", role="agent"
            )

    fake_pdf = io.BytesIO(b"fakepdf-content")
    sha = hashlib.sha256(fake_pdf.getvalue()).hexdigest()

    boletin_id = db.boletines_create(
        conn, uploaded_by=user_id, filename=filename, file_path=f"/tmp/{filename}", file_sha256=sha
    )
    payload = {
        "pages": [
            {
                "page_number": 1,
                "text": "Insc. 2015-015976 ... SOLICITADA POR: ACME ...",
                "char_count": 80,
                "has_images": False,
                "low_confidence": False,
            },
            {
                "page_number": 2,
                "text": "",
                "char_count": 0,
                "has_images": True,
                "low_confidence": True,
            },
        ],
        "metadata": {"bulletin_number": 999},
        "parse_stats": {"total": 5, "matcheables": 3, "figura": 1, "lema": 1, "hermes_pending": 2},
    }
    db.boletines_mark_extracted(
        conn,
        boletin_id=boletin_id,
        pages=pages,
        extraction_payload=payload,
        bulletin_number=999,
        period=None,
        needs_hermes_review=(needs_hermes == 1),
        entries_matcheables=3,
        entries_hermes_pending=2,
    )
    conn.execute(
        "UPDATE boletines SET status=?, hermes_processed_at=? WHERE id=?",
        (status, hermes_processed_at, boletin_id),
    )
    conn.commit()
    return boletin_id


@pytest.fixture()
def sample_entries() -> list[dict]:
    """Lista de dicts de entradas estructuradas de ejemplo."""
    return [
        {
            "expediente": "2015-015976",
            "marca": "TRIPLE MILLONARIO",
            "clase_niza": 35,
            "titular": "RAUL ENRIQUE ARTIGAS",
            "pais": "VENEZUELA",
            "estatus": "PUBLICADA",
            "pagina": 8,
            "fuente": "hermes_vision",
            "confianza": "high",
            "excerpt": "Insc. 2015-015976 del 30 DE OCTUBRE DE 2015",
        },
        {
            "expediente": "2016-013049",
            "marca": "ACME VENEZUELA",
            "clase_niza": 25,
            "titular": "ACME HOLDINGS LLC",
            "pais": "ESTADOS UNIDOS DE AMÉRICA",
            "estatus": "PUBLICADA",
            "pagina": 9,
            "fuente": "hermes_llm",
            "confianza": "medium",
            "excerpt": "ACME VENEZUELA - EN CLASE 25",
        },
    ]

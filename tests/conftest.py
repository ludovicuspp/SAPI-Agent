"""Fixtures compartidos por los tests."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts import db


@pytest.fixture()
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    """Conexión a SQLite en memoria + esquema completo.

    Se inicializa con ``db.init_db`` apuntando a un archivo temporal
    (necesario porque algunos drivers requieren archivo en disco).
    """
    db_file = tmp_path / "test.db"
    db.init_db(db_file)
    conn = db.connect(db_file)
    yield conn
    conn.close()


@pytest.fixture()
def sample_pdf_text() -> str:
    """Texto de ejemplo de un boletín, con marcadores de página y entradas."""
    return (
        "REPÚBLICA BOLIVARIANA DE VENEZUELA\n"
        "MINISTERIO DEL PODER POPULAR DE INDUSTRIAS Y COMERCIO NACIONAL\n"
        "Boletín N° 651 — Caracas, martes 10 de marzo de 2026 — Tomo IX\n"
        "\n"
        "--- página 1 ---\n"
        "SOLICITUDES DE MARCAS DE PRODUCTOS CONCEDIDAS\n"
        "\n"
        "Expediente: 2026-001234\n"
        "Marca: ACME VENEZUELA\n"
        "Clase: 25\n"
        "Titular: ACME HOLDINGS LLC\n"
        "Estatus: CONCEDIDA\n"
        "\n"
        "Expediente: 2026-001235\n"
        "Marca: MARTINEZ Y ASOCIADOS\n"
        "Clase: 35\n"
        "Titular: MARTINEZ & ASOCIADOS C.A.\n"
        "Estatus: PUBLICADA\n"
        "\n"
        "--- página 2 ---\n"
        "Expediente: 2026-001236\n"
        "Marca: GLOBAL TECH SOLUTIONS\n"
        "Clase: 42\n"
        "Titular: GLOBAL TECH HOLDINGS\n"
        "Estatus: CONCEDIDA\n"
        "\n"
        "Expediente: 2026-001237\n"
        "Marca: TECNO MART\n"
        "Clase: 9\n"
        "Titular: COMERCIAL MARTINEZ C.A.\n"
        "Estatus: PUBLICADA\n"
        "\n"
        "--- página 3 ---\n"
        "Expediente: 2026-001238\n"
        "Marca: TEXTIL ACME\n"
        "Clase: 24\n"
        "Titular: TEXTILERIA ACME S.A.\n"
        "Estatus: PUBLICADA\n"
    )

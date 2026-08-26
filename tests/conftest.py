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
def sample_boletin_text() -> str:
    """Texto de ejemplo en formato BPI real (basado en BPI 655).

    Contiene:
    - Sección ``MARCAS CON ORDEN DE PUBLICACIÓN EN PRENSA``
    - 3 entradas con patrón A (marca en línea MAYÚSCULAS)
    - 1 entrada con patrón B (``NOMBRE DE LA MARCA:``)
    - 1 lema comercial (``EN CLASE: LC``)
    """
    return (
        "Boletín de la Propiedad Industrial No. 999\n"
        "_______________________________________________________________________________\n"
        "REPÚBLICA BOLIVARIANA DE VENEZUELA, MINISTERIO DEL PODER POPULAR DE INDUSTRIAS Y COMERCIO NACIONAL\n"
        "Caracas, 24 de febrero de 2026\n"
        "MARCAS CON ORDEN DE PUBLICACIÓN EN PRENSA\n"
        "_______________________________________________________________________________\n"
        "--- página 8 ---\n"
        "Insc. 2015-015976 del 30 DE OCTUBRE DE 2015\n"
        "SOLICITADA POR: RAUL ENRIQUE ARTIGAS Domicilio: BARQUISIMETO, EDO. LARA País:\n"
        "VENEZUELA\n"
        "TRIPLE MILLONARIO\n"
        "EN CLASE: 35\n"
        "PARA DISTINGUIR: LA GESTIÓN DE NEGOCIOS COMERCIALES.\n"
        "_______________________________________________________________________________\n"
        "Insc. 2015-016216 del 06 DE NOVIEMBRE DE 2015\n"
        "SOLICITADA POR: CROCS, INC. Domicilio: COLORADO País: ESTADOS UNIDOS DE AMÉRICA\n"
        "CROCS\n"
        "EN CLASE: 25\n"
        "PARA DISTINGUIR: CALZADO.\n"
        "_______________________________________________________________________________\n"
        "Insc. 2016-013049 del 22 DE AGOSTO DE 2016\n"
        "SOLICITADA POR: ACME HOLDINGS LLC Domicilio: NEW YORK País: ESTADOS UNIDOS DE AMÉRICA\n"
        "ACME VENEZUELA\n"
        "EN CLASE: 25\n"
        "PARA DISTINGUIR: PUBLICACIONES.\n"
        "_______________________________________________________________________________\n"
        "--- página 9 ---\n"
        "Insc. 2018-006650 del 17 DE MAYO DE 2018\n"
        "NOMBRE DE LA MARCA: MARTINEZ INDUSTRIAL\n"
        "SOLICITADA POR: MARTINEZ S.A. Domicilio: CARACAS País: VENEZUELA\n"
        "EN CLASE: 7\n"
        "PARA DISTINGUIR: MAQUINARIA.\n"
        "_______________________________________________________________________________\n"
        "Insc. 2025-011245 del 29 DE OCTUBRE DE 2025\n"
        "SOLICITADA POR: INDUSTRIAS IBERIA, C.A. Domicilio: CAGUA, ESTADO ARAGUA, País:\n"
        "VENEZUELA\n"
        "CALIDAD QUE NO SE OLVIDA\n"
        "EN CLASE: LC\n"
        "PARA DISTINGUIR: LEMA COMERCIAL.\n"
    )


@pytest.fixture()
def sample_pdf_text() -> str:
    """Alias retrocompatible: el texto antiguo en formato 'Expediente:'.

    El parser nuevo NO entiende este formato (es el formato incorrecto
    de la Fase 2 original). Los tests que dependían de él se han
    migrado a ``sample_boletin_text`` y a los nuevos tests.
    """
    return (
        "Expediente: 2026-001234\n"
        "Marca: ACME VENEZUELA\n"
        "Clase: 25\n"
        "Titular: ACME HOLDINGS LLC\n"
    )

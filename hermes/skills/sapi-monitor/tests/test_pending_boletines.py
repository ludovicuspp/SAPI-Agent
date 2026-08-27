"""Tests de ``db_utils.py`` / ``pending_boletines.py`` (consulta SQL)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from db_utils import list_pending_hermes, connect_readonly  # noqa: E402

from conftest import make_boletin  # noqa: E402


def test_list_incluye_pendiente(tmp_db, tmp_db_path):
    make_boletin(tmp_db)
    pending = list_pending_hermes(tmp_db_path)
    assert len(pending) == 1
    assert pending[0].needs_review_pages == 2  # 1 con imagen + 1 bajo


def test_filtra_procesados(tmp_db, tmp_db_path):
    make_boletin(tmp_db, hermes_processed_at="2026-08-27 10:00:00")
    pending = list_pending_hermes(tmp_db_path)
    assert pending == []


def test_filtra_sin_necesidad_review(tmp_db, tmp_db_path):
    make_boletin(tmp_db, needs_hermes=0)
    pending = list_pending_hermes(tmp_db_path)
    assert pending == []


def test_filtra_status_que_no_sea_extracted(tmp_db, tmp_db_path):
    make_boletin(tmp_db, status="failed")
    pending = list_pending_hermes(tmp_db_path)
    assert pending == []


def test_respeta_limit(tmp_db, tmp_db_path):
    for i in range(5):
        make_boletin(tmp_db, filename=f"BPI_{i}.pdf")
    pending = list_pending_hermes(tmp_db_path, limit=3)
    assert len(pending) == 3


def test_ordena_por_id(tmp_db, tmp_db_path):
    ids = [make_boletin(tmp_db, filename=f"BPI_{i}.pdf") for i in range(3)]
    pending = list_pending_hermes(tmp_db_path)
    assert [p.boletin_id for p in pending] == ids


def test_connect_readonly_no_escribe(tmp_db_path):
    conn = connect_readonly(tmp_db_path)
    with pytest.raises(Exception):
        conn.execute("INSERT INTO users(email, password_hash, role) VALUES ('x','h','admin')")
    conn.close()


def test_get_page_texts_devuelve_pages(tmp_db, tmp_db_path):
    bid = make_boletin(tmp_db)
    pages = __import__("db_utils", fromlist=["get_page_texts"]).get_page_texts(tmp_db_path, bid)
    assert len(pages) == 2


def test_get_page_texts_vacio_si_no_existe(tmp_db_path):
    pages = __import__("db_utils", fromlist=["get_page_texts"]).get_page_texts(tmp_db_path, 9999)
    assert pages == []

"""Tests del análisis retroactivo de marcas nuevas (matching_service)."""
from __future__ import annotations

import json

from scripts import db
from scripts.matcher import combined
from scripts.matcher.distinguish import (
    products_intersect,
    tokenize_distinguish,
)
from scripts.orchestration.matching_service import (
    _entries_from_extraction_json,
    analyze_boletines_for_user,
    match_watchlist_for_boletin,
)


def _make_extracted_boletin(conn, user_id: int, text: str) -> int:
    """Crea y marca un boletín extraído con el texto indicado."""
    bid = db.boletines_create(
        conn, user_id, "test.pdf", "/tmp/test.pdf", "b" * 64
    )
    db.boletines_mark_extracted(
        conn,
        bid,
        pages=1,
        extraction_payload={
            "pages": [{"page_number": 1, "text": text}],
            "metadata": {"bulletin_number": 999, "period": None, "tomo": None},
            "parse_stats": {"total": 1, "matcheables": 1},
        },
        bulletin_number=999,
        period=None,
        needs_hermes_review=False,
        entries_matcheables=1,
    )
    conn.commit()
    return bid


_MARCA_TEXT = (
    "MARCAS CON ORDEN DE PUBLICACIÓN EN PRENSA\n"
    "--- página 8 ---\n"
    "Insc. 2026-004496 del 12 DE ENERO DE 2026\n"
    "SOLICITADA POR: TITULAR SA Domicilio: CARACAS País: VENEZUELA\n"
    "RAPTOR\n"
    "EN CLASE: 12\n"
    "PARA DISTINGUIR: VEHÍCULOS Y AUTOMÓVILES.\n"
)


def test_analyze_portfolio_detects_by_registro(tmp_db):
    """Una marca nueva con #registro igual al expediente de la entry
    genera detección own_status en el análisis retroactivo."""
    uid = db.users_create(tmp_db, "u@x.y", "h")
    bid = _make_extracted_boletin(tmp_db, uid, _MARCA_TEXT)
    db.portfolio_add(tmp_db, uid, "RAPTOR", registro="2026-004496")

    res = analyze_boletines_for_user(tmp_db, uid, run_watchlist=False)
    assert res["boletines_analizados"] == 1
    assert res["detecciones_creadas"] == 1

    detections = db.detections_list_for_user(tmp_db, uid)
    assert len(detections) == 1
    assert detections[0].portfolio_id is not None
    assert detections[0].mark_name == "RAPTOR"
    assert detections[0].matched_with == "RAPTOR"
    assert detections[0].boletin_id == bid
    assert detections[0].match_kind == "own_status"


def test_analyze_is_idempotent(tmp_db):
    """Re-ejecutar el análisis no duplica detecciones."""
    uid = db.users_create(tmp_db, "u@x.y", "h")
    _make_extracted_boletin(tmp_db, uid, _MARCA_TEXT)
    db.portfolio_add(tmp_db, uid, "RAPTOR", registro="2026-004496")

    first = analyze_boletines_for_user(tmp_db, uid, run_watchlist=False)
    second = analyze_boletines_for_user(tmp_db, uid, run_watchlist=False)
    assert first["detecciones_creadas"] == 1
    assert second["detecciones_creadas"] == 0
    assert len(db.detections_list_for_user(tmp_db, uid)) == 1


def test_analyze_portfolio_no_registro_no_match(tmp_db):
    """Portfolio sin #registro ni #solicitud: el análisis retroactivo
    no genera detección aunque el expediente de la entry coincida
    con el del portafolio."""
    uid = db.users_create(tmp_db, "u@x.y", "h")
    _make_extracted_boletin(tmp_db, uid, _MARCA_TEXT)
    db.portfolio_add(tmp_db, uid, "RAPTOR")  # sin #registro/#solicitud

    res = analyze_boletines_for_user(tmp_db, uid, run_watchlist=False)
    assert res["detecciones_creadas"] == 0


def test_analyze_watchlist_name_class_distingue(tmp_db):
    """Watchlist con nombre + clase + distingue en común: matchea."""
    uid = db.users_create(tmp_db, "u@x.y", "h")
    bid = _make_extracted_boletin(tmp_db, uid, _MARCA_TEXT)
    db.watchlist_add(
        tmp_db, uid, "RAPTOR", class_nice=12,
        productos_servicios="VEHÍCULOS DE MOTOR",
    )

    res = analyze_boletines_for_user(tmp_db, uid, run_portfolio=False)
    assert res["detecciones_creadas"] == 1
    detections = db.detections_list_for_user(tmp_db, uid)
    assert detections[0].watchlist_id is not None
    assert detections[0].match_kind == "similar"
    assert detections[0].boletin_id == bid


def test_analyze_watchlist_class_mismatch_no_match(tmp_db):
    """Watchlist con clase distinta a la entry: no matchea."""
    uid = db.users_create(tmp_db, "u@x.y", "h")
    _make_extracted_boletin(tmp_db, uid, _MARCA_TEXT)
    # Entry RAPTOR es clase 12; la watchlist RAPTORFLEX es clase 17.
    db.watchlist_add(
        tmp_db, uid, "RAPTORFLEX", class_nice=17,
        productos_servicios="VEHÍCULOS Y AUTOMÓVILES",
    )

    res = analyze_boletines_for_user(tmp_db, uid, run_portfolio=False)
    assert res["detecciones_creadas"] == 0
    assert db.detections_list_for_user(tmp_db, uid) == []


def test_analyze_watchlist_distingue_mismatch_no_match(tmp_db):
    """Watchlist con nombre + clase iguales pero distingue sin
    intersección de tokens: no matchea."""
    uid = db.users_create(tmp_db, "u@x.y", "h")
    _make_extracted_boletin(tmp_db, uid, _MARCA_TEXT)
    # Entry: VEHÍCULOS Y AUTOMÓVILES. Watchlist: CALZADO.
    db.watchlist_add(
        tmp_db, uid, "RAPTOR", class_nice=12,
        productos_servicios="CALZADO",
    )

    res = analyze_boletines_for_user(tmp_db, uid, run_portfolio=False)
    assert res["detecciones_creadas"] == 0


def test_analyze_watchlist_distingue_fallback_no_match(tmp_db):
    """Si la entry no trae distingue pero watchlist sí y la similitud de
    nombre es baja (<fuzzy), no hay match."""
    text_sin_distingue = (
        "MARCAS CON ORDEN DE PUBLICACIÓN EN PRENSA\n"
        "--- página 8 ---\n"
        "Insc. 2026-004496 del 12 DE ENERO DE 2026\n"
        "SOLICITADA POR: TITULAR SA Domicilio: CARACAS País: VENEZUELA\n"
        "RAPTOR\n"
        "EN CLASE: 12\n"
    )
    uid = db.users_create(tmp_db, "u@x.y", "h")
    _make_extracted_boletin(tmp_db, uid, text_sin_distingue)
    db.watchlist_add(
        tmp_db, uid, "OTRA", class_nice=12,
        productos_servicios="VEHÍCULOS Y AUTOMÓVILES",
    )

    res = analyze_boletines_for_user(tmp_db, uid, run_portfolio=False)
    assert res["detecciones_creadas"] == 0


def test_entries_from_extraction_json_parses(tmp_db):
    """Re-leer entries desde el extraction_json devuelve la marca."""
    uid = db.users_create(tmp_db, "u@x.y", "h")
    bid = _make_extracted_boletin(tmp_db, uid, _MARCA_TEXT)
    row = _scalar(tmp_db, "SELECT extraction_json FROM boletines WHERE id=?", bid)
    entries = _entries_from_extraction_json(row)
    marcas = [e.marca for e in entries if e.marca]
    assert "RAPTOR" in marcas


def test_tokenize_distinguish_basic():
    """Stopwords se filtran; acentos se colapsan; palabras <3 se omiten."""
    toks = tokenize_distinguish("LA GESTIÓN DE NEGOCIOS COMERCIALES")
    assert toks == {"gestion", "negocios", "comerciales"}
    toks = tokenize_distinguish("CALZADO")
    assert toks == {"calzado"}
    toks = tokenize_distinguish(None)
    assert toks == set()


def test_products_intersect_basic():
    """Intersección ≥1 token: True; sin tokens compartidos: False;
    alguno vacío: None."""
    assert products_intersect(
        "VEHÍCULOS Y AUTOMÓVILES", "VEHÍCULOS DE MOTOR",
    ) is True
    assert products_intersect(
        "VEHÍCULOS Y AUTOMÓVILES", "CALZADO",
    ) is False
    assert products_intersect(None, "CALZADO") is None
    assert products_intersect("CALZADO", "") is None


def test_match_watchlist_direct(tmp_db):
    """match_watchlist_for_boletin persiste detecciones de tipo similar
    aplicando la regla AND (nombre + clase + distingue)."""
    uid = db.users_create(tmp_db, "u@x.y", "h")
    bid = _make_extracted_boletin(tmp_db, uid, _MARCA_TEXT)
    db.watchlist_add(
        tmp_db, uid, "RAPTOR", class_nice=12,
        productos_servicios="VEHÍCULOS Y AUTOMÓVILES",
    )

    row = _scalar(tmp_db, "SELECT extraction_json FROM boletines WHERE id=?", bid)
    entries = _entries_from_extraction_json(row)
    matcheable = [e for e in entries if e.matcheable]
    th = combined.Thresholds.from_settings(85, 80)
    created = match_watchlist_for_boletin(tmp_db, uid, bid, matcheable, th)
    assert created == 1


def _scalar(conn, sql, *params):
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return row[0]

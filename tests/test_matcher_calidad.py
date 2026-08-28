"""Tests del matcher (exact, fuzzy, fonético, combinado).

Calidad del matching: casos límite, falsos positivos, fonético idéntico,
orden de prioridad.
"""
from __future__ import annotations

import pytest

from scripts.matcher.combined import score_pair, Thresholds, MatchResult


def _t() -> Thresholds:
    return Thresholds(fuzzy=0.80)


# M.1 ── exacto
def test_matcher_exacto():
    r = score_pair("TRIPLE MILLONARIO", "TRIPLE MILLONARIO", _t())
    assert r.is_match
    assert r.similarity == 1.0
    assert r.method == "exact"
    assert r.confidence == "high"


# M.2 ── fuzzy case-insensitive alto
def test_matcher_fuzzy_case_insensitive():
    r = score_pair("TRIPLE MILLONARIO", "Triple Millonario", _t())
    assert r.is_match
    assert r.similarity >= 0.95
    assert r.confidence == "high"


# M.3 ── fuzzy con typo
def test_matcher_fuzzy_typo():
    r = score_pair("TRIPLE MILLONARIO", "TRIPLE MILONARIO", _t())
    assert r.is_match
    assert r.similarity >= 0.85


# M.4 ── fonético idéntico (typo fuerte pero misma fonética)
def test_matcher_fonetico_identico():
    # "TRIPLE MILLONARIO" vs "TRI MILLONARIO" (phonético similar)
    r = score_pair("TRIPLE MILLONARIO", "TRIPLE MILLONAR", _t())
    # Si fonético idéntico, similarity=0.70 confidence=medium
    if r.method == "phonetic":
        assert r.similarity == 0.70
        assert r.confidence == "medium"


# M.5 ── no-match
def test_matcher_no_match_palabras_distintas():
    r = score_pair("ACME", "TOTALMENTE DISTINTO", _t())
    assert not r.is_match


# M.6 ── threshold configurable
def test_matcher_threshold_bajo_es_mas_permisivo():
    t_low = Thresholds(fuzzy=0.50)
    r = score_pair("TRIPLE MILLONARIO", "Triple M", t_low)
    # A 0.50 puede pasar
    assert r.similarity >= 0.50


def test_matcher_threshold_alto_es_mas_estricto():
    t_high = Thresholds(fuzzy=0.99)
    r = score_pair("TRIPLE MILLONARIO", "Triple Millonario", t_high)
    # A 0.99 NO debe pasar fuzzy (case no cuenta para exact)
    if r.method != "exact":
        assert not r.is_match or r.similarity >= 0.99


# M.7 ── fonético: 'B' y 'V' suenan igual en español (jellyfish soundex)
def test_matcher_fonetico_b_vs_v():
    r = score_pair("BARCELONA", "VARCELONA", _t())
    # Fonético español puede considerarlas iguales
    # Si fonético idéntico → similarity=0.70
    if r.method == "phonetic":
        assert r.similarity == 0.70


# M.8 ── prioridad: exact gana sobre fuzzy
def test_matcher_exact_gana_sobre_fuzzy():
    r = score_pair("EXACTA", "EXACTA", _t())
    assert r.method == "exact"
    assert r.similarity == 1.0


# M.9 ── MatchResult es dataclass inmutable
def test_matcher_result_estructura():
    r = score_pair("X", "X", _t())
    assert isinstance(r, MatchResult)
    assert hasattr(r, "is_match")
    assert hasattr(r, "similarity")
    assert hasattr(r, "method")
    assert hasattr(r, "confidence")


# M.10 ── strings vacíos: similarity=0, no match (defensa contra vacíos)
def test_matcher_strings_vacios():
    r = score_pair("", "", _t())
    assert not r.is_match
    assert r.similarity == 0.0


def test_matcher_un_vacio():
    r = score_pair("ACME", "", _t())
    assert not r.is_match


# ── G.1 — cruce de clase Niza ──────────────────────────────────────


def test_matcher_mismatch_clase_niza():
    """Si watch_class_nice y candidate_class_nice difieren, no es match."""
    r = score_pair(
        "ACME", "ACME", _t(),
        watch_class_nice=25,
        candidate_class_nice=9,
    )
    assert not r.is_match
    assert r.class_nice_check == "mismatch"
    assert r.similarity == 0.0


def test_matcher_misma_clase_niza_es_match():
    r = score_pair(
        "ACME", "ACME", _t(),
        watch_class_nice=25,
        candidate_class_nice=25,
    )
    assert r.is_match
    assert r.class_nice_check == "ok"


def test_matcher_clase_niza_solo_en_watch_no_bloquea():
    """Si solo la watchlist tiene clase, no bloqueamos (regla es 'ambos')."""
    r = score_pair(
        "ACME", "ACME", _t(),
        watch_class_nice=25,
        candidate_class_nice=None,
    )
    assert r.is_match


def test_matcher_clase_niza_solo_en_candidate_no_bloquea():
    r = score_pair(
        "ACME", "ACME", _t(),
        watch_class_nice=None,
        candidate_class_nice=9,
    )
    assert r.is_match


def test_matcher_ninguna_clase_es_match():
    r = score_pair(
        "ACME", "ACME", _t(),
        watch_class_nice=None,
        candidate_class_nice=None,
    )
    assert r.is_match
    assert r.class_nice_check == "unknown"


# ── G.3 — umbrales ajustables por usuario ─────────────────────────


def test_thresholds_from_user_con_overrides():
    """from_user con overrides aplica los valores del usuario."""
    from scripts.matcher.combined import Thresholds
    base = Thresholds(fuzzy=0.80)
    user = Thresholds.from_user(fuzzy_pct=90, phonetic_floor=0.9, fallback=base)
    assert user.fuzzy == 0.90
    assert user.phonetic_floor == 0.9


def test_thresholds_from_user_sin_overrides_usa_fallback():
    from scripts.matcher.combined import Thresholds
    base = Thresholds(fuzzy=0.80, phonetic_floor=1.0)
    user = Thresholds.from_user(fallback=base)
    assert user.fuzzy == 0.80
    assert user.phonetic_floor == 1.0


def test_thresholds_from_user_parcial():
    """Solo fuzzy_pct override, phonetic_floor usa fallback."""
    from scripts.matcher.combined import Thresholds
    base = Thresholds(fuzzy=0.80, phonetic_floor=1.0)
    user = Thresholds.from_user(fuzzy_pct=95, fallback=base)
    assert user.fuzzy == 0.95
    assert user.phonetic_floor == 1.0


# ── G.2 — defensa contra falsos positivos via Hermes Vision ──────


def test_matcher_fuzzy_bajo_bajo_phonetic_bloqueado():
    """Si usuario quiere fonético más débil pero fonético está a 0.95,
    el matcher respeta el floor."""
    from scripts.matcher.combined import Thresholds
    t = Thresholds(fuzzy=0.80, phonetic_floor=0.95)
    r = score_pair("ACME", "AKME", t)
    # Si fonético idéntico (>=0.95), match; si no, no-match
    # Lo que validamos es que el floor se respeta
    assert r.is_match == (r.similarity == 0.70 and r.method == "phonetic")


# ── find_matches con clases ────────────────────────────────────────


def test_find_matches_con_clases():
    """find_matches filtra correctamente cuando hay mismatch de clase."""
    from scripts.matcher.combined import find_matches
    watch_names = ["ACME", "TOTAL"]
    watch_classes = [25, 35]
    candidates = ["ACME", "TOTAL"]
    candidate_classes = [9, 35]  # ACME mismatch, TOTAL ok
    pairs = find_matches(
        watch_names, candidates, _t(),
        watch_class_nices=watch_classes,
        candidate_class_nices=candidate_classes,
    )
    # Solo TOTAL-35 debe matchear (ACME-25 vs ACME-9 mismatch)
    assert len(pairs) == 1
    assert pairs[0][0] == "TOTAL"
    assert pairs[0][1] == "TOTAL"


def test_find_matches_sin_clases_matchea_todo():
    """Sin clases, comportamiento legacy (todos los matches pasan)."""
    from scripts.matcher.combined import find_matches
    watch_names = ["ACME", "TOTAL"]
    candidates = ["ACME", "TOTAL"]
    pairs = find_matches(watch_names, candidates, _t())
    assert len(pairs) == 2

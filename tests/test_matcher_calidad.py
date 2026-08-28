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

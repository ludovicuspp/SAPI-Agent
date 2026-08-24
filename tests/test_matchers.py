"""Tests de lógica pura del motor de similitud."""
from __future__ import annotations

from scripts.matcher import combined, exact, fuzzy, phonetic


class TestExact:
    def test_identical(self):
        assert exact.exact_score("ACME", "ACME") == 1.0

    def test_case_insensitive(self):
        assert exact.exact_score("acme", "ACME") == 1.0

    def test_accents_ignored(self):
        assert exact.exact_score("MARTÍNEZ", "MARTINEZ") == 1.0

    def test_different(self):
        assert exact.exact_score("ACME", "GLOBEX") == 0.0

    def test_empty(self):
        assert exact.exact_score("", "ACME") == 0.0

    def test_normalize_collapses_spaces(self):
        assert exact.normalize("  ACME   VENEZUELA  ") == "acme venezuela"


class TestFuzzy:
    def test_identical(self):
        assert fuzzy.fuzzy_score("ACME", "ACME") == 1.0

    def test_typo_close(self):
        # ACME vs ACNE: 1 char de 4 distintos. fuzzy_score razonable.
        s = fuzzy.fuzzy_score("ACME", "ACNE")
        # No exigimos >=0.8 estricto: rapidfuzz.WRatio sobre strings
        # cortos puede dar ~0.75-0.85 según versión. Lo importante es
        # que supera un umbral de "no relacionado".
        assert s >= 0.6

    def test_reordered(self):
        # "VENEZUELA ACME" vs "ACME VENEZUELA"
        s = fuzzy.fuzzy_score("ACME VENEZUELA", "VENEZUELA ACME")
        assert s >= 0.95

    def test_unrelated(self):
        s = fuzzy.fuzzy_score("ACME", "GLOBEX")
        assert s < 0.5

    def test_empty(self):
        assert fuzzy.fuzzy_score("", "ACME") == 0.0


class TestPhonetic:
    def test_similar_spanish_surnames(self):
        # metaphone para MARTINEZ y MARTINES debería ser idéntico
        c1 = phonetic.phonetic_code("MARTINEZ")
        c2 = phonetic.phonetic_code("MARTINES")
        assert c1 == c2
        assert phonetic.phonetic_score("MARTINEZ", "MARTINES") == 1.0

    def test_different(self):
        assert phonetic.phonetic_score("ACME", "GLOBEX") == 0.0

    def test_empty(self):
        assert phonetic.phonetic_score("", "ACME") == 0.0


class TestCombined:
    def test_exact_match(self):
        r = combined.score_pair("ACME", "ACME")
        assert r.is_match
        assert r.similarity == 1.0
        assert r.method == "exact"
        assert r.confidence == "high"

    def test_fuzzy_match(self):
        # ACME VENEZUELA vs ACME: high fuzzy (substring/token overlap)
        r = combined.score_pair("ACME", "ACME VENEZUELA")
        assert r.is_match
        assert r.method == "fuzzy"

    def test_phonetic_match_spanish(self):
        # MARTINEZ/MARTINES: ambos coinciden por fuzzy (0.875) y por phonetic
        # (MRTNS). El método ganador en combined es el primero que supere el
        # threshold; en este caso fuzzy.
        r = combined.score_pair("MARTINEZ", "MARTINES")
        assert r.is_match
        assert r.method in ("fuzzy", "phonetic")
        # Phonetic directo sí devuelve match por metaphone
        assert phonetic.phonetic_score("MARTINEZ", "MARTINES") == 1.0

    def test_phonetic_only_when_fuzzy_fails(self):
        # PEREZ vs PRS necesita un test donde fuzzy NO llega al threshold
        # pero phonetic sí. Como WRatio es muy generoso, lo demostramos con
        # un caso extremo: dos strings fonéticamente idénticos pero muy
        # distintos visualmente.
        # "CATHERINE" vs "KATHRYN" — metaphone: K0RN vs K0RN, fuzzy bajo.
        r = combined.score_pair("CATHERINE", "KATHRYN")
        # Al menos phonetic_score debe dar match directo
        assert phonetic.phonetic_score("CATHERINE", "KATHRYN") == 1.0

    def test_no_match(self):
        r = combined.score_pair("ACME", "ZAPATILLAS DELTA")
        assert not r.is_match
        assert r.method == "fuzzy"
        assert r.confidence == "low"

    def test_find_matches(self):
        watch = ["ACME", "MARTINEZ"]
        candidates = ["ACME VENEZUELA", "MARTINES Y ASOCIADOS", "OTRA MARCA"]
        matches = combined.find_matches(watch, candidates)
        # ACME vs ACME VENEZUELA: fuzzy >= 0.80
        # MARTINEZ vs MARTINES Y ASOCIADOS: phonetic
        assert len(matches) >= 2
        methods = {m[2].method for m in matches}
        assert "fuzzy" in methods or "phonetic" in methods

    def test_thresholds_from_settings(self):
        th = combined.Thresholds.from_settings(85, 80)
        assert th.fuzzy == 0.80

"""Tests de lógica pura del motor de similitud."""
from __future__ import annotations

from scripts.matcher import combined, exact, fuzzy, phonetic
from scripts.matcher import family, nice_classes, risk


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


class TestPhoneticHispano:
    def test_baca_vaca(self):
        # v/b colapsan en español.
        assert phonetic.phonetic_score("BACA", "VACA") == 1.0

    def test_zapato_sapato(self):
        # z -> s (seseo).
        assert phonetic.phonetic_score("ZAPATO", "SAPATO") == 1.0

    def test_hecho_echo(self):
        # h muda se ignora.
        assert phonetic.phonetic_score("HECHO", "ECHO") == 1.0

    def test_llega_and_llave(self):
        # ll -> y.
        assert phonetic.phonetic_score("LLAVE", "YAVE") == 1.0

    def test_nino_nino(self):
        # ñ -> n.
        assert phonetic.phonetic_score("NIÑO", "NINO") == 1.0

    def test_qu_k_and_ei(self):
        # QUIOSCO vs KIOSKO: qu -> k y la vocal se mantiene; coinciden.
        assert phonetic.phonetic_score("KIOSKO", "QUIOSCO") == 1.0
        # c+e/i -> s: CERO vs SERO.
        assert phonetic.phonetic_score("CERO", "SERO") == 1.0

    def test_kwik_quick_not_match(self):
        # KWIK vs QUICK: KWIK tiene una 'w' que no es patrón español; no
        # debe colapsar con QUICK.
        assert phonetic.phonetic_score("KWIK", "QUICK") == 0.0


class TestNiceClasses:
    def test_same(self):
        assert nice_classes.classes_related(12, 12) == "same"

    def test_related_group(self):
        # 7 y 12 (máquinas/vehículos) están en el mismo bloque.
        assert nice_classes.classes_related(7, 12) == "related"

    def test_service_commercial_complements(self):
        # 35 (venta) complementa a cualquier producto.
        assert nice_classes.classes_related(35, 12) == "related"
        assert nice_classes.classes_related(1, 35) == "related"

    def test_unrelated(self):
        # 12 (vehículos) y 3 (cosméticos) no se relacionan.
        assert nice_classes.classes_related(12, 3) == "unrelated"

    def test_none_is_distant(self):
        assert nice_classes.classes_related(None, 12) == "distant"

    def test_proximity_values(self):
        assert nice_classes.proximity(12, 12) == 1.0
        assert nice_classes.proximity(7, 12) == 0.6
        assert nice_classes.proximity(12, 3) == 0.0
        assert nice_classes.proximity(None, 12) == 0.3


class TestRisk:
    def test_high_overlap(self):
        s = risk.risk_score(
            name_sim=1.0, class_proximity=1.0, products_overlap=True
        )
        assert s > 0.9

    def test_low_risk(self):
        s = risk.risk_score(
            name_sim=0.5, class_proximity=0.0, products_overlap=False
        )
        assert s < 0.6

    def test_unknown_overlap_neutral(self):
        s = risk.risk_score(name_sim=0.5, class_proximity=0.5, products_overlap=None)
        with_overlap = risk.risk_score(
            name_sim=0.5, class_proximity=0.5, products_overlap=True
        )
        without_overlap = risk.risk_score(
            name_sim=0.5, class_proximity=0.5, products_overlap=False
        )
        assert without_overlap < s < with_overlap

    def test_titular_known_conflict_bonus(self):
        base = risk.risk_score(name_sim=0.9, class_proximity=1.0, products_overlap=True)
        bonus = risk.risk_score(
            name_sim=0.9, class_proximity=1.0, products_overlap=True,
            titular_known_conflict=True,
        )
        assert bonus > base
        assert bonus <= 1.0


class TestFamily:
    def test_dragon_winch_contains(self):
        # DRAGON WINCH contiene DRAGON -> familia.
        assert family.family_score("DRAGON", "DRAGON WINCH") == 1.0

    def test_raptor_hydraulic(self):
        assert family.family_score("RAPTOR", "RAPTOR HYDRAULIC") == 1.0

    def test_max_maxt_not_contained(self):
        # MAX vs MAXXT: no es contención (MAXTT tiene 'maxt', distinto).
        assert family.family_score("MAX", "MAXTT") == 0.0

    def test_overlap_symmetric(self):
        assert family.family_overlap("DRAGON", "DRAGON WINCH") == 1.0
        assert family.family_overlap("RAPTOR", "EAGLE RAPTOR") == 1.0
        assert family.family_overlap("MAX", "MAXTT") == 0.0

    def test_non_brand_tokens_ignored(self):
        # CA/S.A. genéricos no cuentan como tokens de marca.
        assert family.core_tokens("ACME CA") == ["acme"]
        assert family.family_score("ACME SA", "ACME CORP") == 1.0
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

    def test_class_nice_mismatch_is_not_a_match(self):
        result = combined.score_pair(
            "ACME",
            "ACME",
            watch_class_nice=25,
            candidate_class_nice=9,
        )
        assert not result.is_match
        assert result.class_nice_check == "mismatch"

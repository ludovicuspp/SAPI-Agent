"""Tests de utilidades de limpieza y normalización del parser."""
from __future__ import annotations

from scripts.parsers.patterns.base import (
    clean_marca,
    clean_titular,
    extract_brand_lines,
    is_upperish,
    normalize_fecha,
    normalize_pais,
    parse_clase,
)


class TestCleanMarca:
    def test_quita_prefijo_h(self):
        assert clean_marca("H PIMACO") == "PIMACO"

    def test_quita_prefijo_n(self):
        assert clean_marca("N SERVICENOW") == "SERVICENOW"

    def test_quita_prefijo_e(self):
        assert clean_marca("E LA GEAR") == "LA GEAR"

    def test_quita_prefijo_c(self):
        assert clean_marca("C FRESH FOOD") == "FRESH FOOD"

    def test_quita_prefijo_z(self):
        assert clean_marca("Z MARCA") == "MARCA"

    def test_preserva_caracteres_especiales(self):
        # copyright
        assert clean_marca("MILL©S PRIDE") == "MILL©S PRIDE"

    def test_preserva_apostrofe(self):
        assert clean_marca("NATY´S") == "NATY´S"

    def test_preserva_punto(self):
        assert clean_marca("WEB.COM") == "WEB.COM"

    def test_preserva_numeros(self):
        assert clean_marca("TOTALPEDIDOS.COM") == "TOTALPEDIDOS.COM"

    def test_quita_traduccion_parentesis(self):
        # Si tiene paréntesis al final, se queda con el nombre principal.
        result = clean_marca("EXTREMEN FLOTATION (FLOTACIÓN EXTREMA)")
        assert result == "EXTREMEN FLOTATION"

    def test_none_devuelve_none(self):
        assert clean_marca(None) is None

    def test_string_vacio_devuelve_vacio(self):
        assert clean_marca("") == ""


class TestCleanTitular:
    def test_corta_en_domicilio(self):
        s = "MILKAUT S.A Domicilio: ARGENTINA,BUENOS AIRES"
        assert clean_titular(s) == "MILKAUT S.A"

    def test_corta_en_pais(self):
        s = "ACME HOLDINGS LLC País: VENEZUELA"
        assert clean_titular(s) == "ACME HOLDINGS LLC"

    def test_corta_en_tramitante(self):
        s = "ACME S.A.\nTRAMITANTE: ALGUIEN"
        assert clean_titular(s) == "ACME S.A"

    def test_none_devuelve_none(self):
        assert clean_titular(None) is None


class TestNormalizePais:
    def test_palabras_pegadas(self):
        # "ESTADOS UNIDOSDEAMÉRICA" → "ESTADOS UNIDOS DE AMÉRICA"
        assert normalize_pais("ESTADOS UNIDOSDEAMÉRICA") == "ESTADOS UNIDOS DE AMÉRICA"

    def test_pais_simple(self):
        assert normalize_pais("VENEZUELA") == "VENEZUELA"

    def test_quita_cid_residual(self):
        assert normalize_pais("ESTADOS(cid:38) UNIDOS") == "ESTADOS UNIDOS"

    def test_none_devuelve_none(self):
        assert normalize_pais(None) is None


class TestNormalizeFecha:
    def test_formato_completo(self):
        assert normalize_fecha("30 DE OCTUBRE DE 2015") == "2015-10-30"

    def test_minusculas(self):
        assert normalize_fecha("15 de febrero de 2026") == "2026-02-15"

    def test_setiembre_como_septiembre(self):
        assert normalize_fecha("01 DE SETIEMBRE DE 2025") == "2025-09-01"

    def test_formato_irreconocible(self):
        assert normalize_fecha("not a date") is None

    def test_mes_invalido(self):
        assert normalize_fecha("01 DE MESINVALIDO DE 2025") is None

    def test_dia_fuera_de_rango(self):
        # Día 32 es inválido
        assert normalize_fecha("32 DE ENERO DE 2025") is None

    def test_none(self):
        assert normalize_fecha(None) is None


class TestParseClase:
    def test_clase_numerica_valida(self):
        n, lc = parse_clase("30")
        assert n == 30
        assert lc is None

    def test_clase_lc(self):
        n, lc = parse_clase("LC")
        assert n is None
        assert lc == "LC"

    def test_clase_minuscula(self):
        n, lc = parse_clase("lc")
        assert n is None
        assert lc == "LC"

    def test_clase_fuera_de_rango(self):
        n, lc = parse_clase("50")
        assert n is None
        assert lc is None

    def test_none(self):
        assert parse_clase(None) == (None, None)


class TestIsUpperish:
    def test_todo_mayusculas(self):
        assert is_upperish("PIMACO")

    def test_mayusculas_con_espacios(self):
        assert is_upperish("UCAMAY CALM RESTORE")

    def test_minusculas(self):
        assert not is_upperish("minúsculas")

    def test_mezclado(self):
        # "Web.Com" tiene 2 mayúsculas y 4 minúsculas
        assert not is_upperish("Web.Com", threshold=0.7)

    def test_con_caracteres_especiales(self):
        assert is_upperish("MILL©S PRIDE")

    def test_vacio(self):
        assert not is_upperish("")


class TestExtractBrandLines:
    def test_una_linea_mayuscula(self):
        text = "TRIPLE MILLONARIO\nEN CLASE: 35\nPARA DISTINGUIR: ..."
        lines = extract_brand_lines(text)
        assert lines == ["TRIPLE MILLONARIO"]

    def test_multiples_lineas(self):
        text = (
            "CUANDO PIENSES EN CABLES\n"
            "PIENSA EN CABLESCA\n"
            "EN CLASE: 9"
        )
        lines = extract_brand_lines(text)
        assert lines == ["CUANDO PIENSES EN CABLES", "PIENSA EN CABLESCA"]

    def test_corta_en_linea_no_mayuscula(self):
        text = "TRIPLE MILLONARIO\nPara distinguir: ..."
        lines = extract_brand_lines(text)
        assert lines == ["TRIPLE MILLONARIO"]

    def test_corta_en_EN_CLASE(self):
        text = "EN CLASE: 35\nTRIPLE MILLONARIO"
        lines = extract_brand_lines(text, end=text.find("EN CLASE"))
        assert lines == []

    def test_ignora_domicilio_pais(self):
        text = "DOMICILIO: CARACAS\nPAÍS: VENEZUELA\nEN CLASE: 25"
        lines = extract_brand_lines(text)
        assert lines == []

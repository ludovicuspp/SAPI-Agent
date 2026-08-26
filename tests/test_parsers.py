"""Tests de los parsers del boletín.

Usa ``sample_boletin_text`` (formato BPI real con ``Insc.``) en lugar del
formato ``Expediente:`` inventado de la Fase 2.
"""
from __future__ import annotations

import pytest

from scripts.parsers import boletin_header
from scripts.parsers.marca_entry import MarcaEntryParser


class TestBoletinHeader:
    def test_detect_number_with_grado(self):
        md = boletin_header.detect("Boletín N° 651")
        assert md.bulletin_number == 651

    def test_detect_number_without_grado(self):
        md = boletin_header.detect("BOLETIN 651")
        assert md.bulletin_number == 651

    def test_detect_period(self):
        text = "Boletín N° 651 Caracas, martes 10 de marzo de 2026"
        md = boletin_header.detect(text)
        assert md.period is not None
        assert "Marzo" in md.period
        assert "2026" in md.period

    def test_detect_tomo(self):
        md = boletin_header.detect("Tomo IX")
        assert md.tomo == "IX"

    def test_detect_nothing(self):
        md = boletin_header.detect("texto sin datos relevantes")
        assert md.bulletin_number is None
        assert md.period is None
        assert md.tomo is None

    def test_secciones_catalogo(self):
        """Verifica que las secciones del catálogo están registradas."""
        assert len(boletin_header.SECCIONES) >= 20
        assert boletin_header.SECCIONES["MARCAS CON ORDEN DE PUBLICACIÓN EN PRENSA"] == "PUBLICADA"
        assert boletin_header.SECCIONES["MARCAS DE PRODUCTOS CONCEDIDAS"] == "CONCEDIDA"
        assert boletin_header.SECCIONES["MARCAS NEGADAS"] == "NEGADA"
        assert boletin_header.SECCIONES["RENOVACIONES DE MARCAS Y OTROS"] == "RENOVADA"


class TestDetectCurrentSection:
    def test_section_before_position(self):
        text = (
            "MARCAS CON ORDEN DE PUBLICACIÓN EN PRENSA\n"
            "Insc. 2026-001 del 01 DE ENERO DE 2026\n"
            "SOLICITADA POR: X\n"
            "MARCA TEST\n"
            "EN CLASE: 25\n"
        )
        # Posición al inicio del bloque Insc.
        idx = text.find("Insc.")
        assert boletin_header.detect_current_section(text, idx) == "PUBLICADA"

    def test_section_after_position(self):
        text = (
            "Insc. 2026-001 del 01 DE ENERO DE 2026\n"
            "MARCAS DE PRODUCTOS CONCEDIDAS\n"  # viene después
            "MARCA TEST\n"
        )
        idx = text.find("Insc.")
        # La sección está DESPUÉS de la inscripción, no antes → None
        assert boletin_header.detect_current_section(text, idx) is None

    def test_no_section_detected(self):
        text = "Texto sin secciones reconocibles"
        assert boletin_header.detect_current_section(text, len(text)) is None

    def test_multiple_sections(self):
        """La función debe quedarse con la última sección antes de la posición."""
        text = (
            "MARCAS CON ORDEN DE PUBLICACIÓN EN PRENSA\n"
            "Insc. 2026-001 del 01 DE ENERO DE 2026\n"
            "MARCAS NEGADAS\n"
            "Insc. 2026-002 del 02 DE ENERO DE 2026\n"
        )
        idx = text.find("2026-002")
        assert boletin_header.detect_current_section(text, idx) == "NEGADA"


class TestMarcaEntryParser:
    def test_parses_pattern_a(self, sample_boletin_text):
        """Pattern A: Insc. + SOLICITADA POR + Marca-línea + EN CLASE."""
        parser = MarcaEntryParser()
        entries, stats = parser.parse_with_stats(sample_boletin_text)
        # Hay 3 entradas con patrón A (TRIPLE MILLONARIO, CROCS, ACME VENEZUELA)
        assert stats.pattern_a_count >= 3
        marcas = {e.marca for e in entries if e.marca}
        assert "TRIPLE MILLONARIO" in marcas
        assert "CROCS" in marcas
        assert "ACME VENEZUELA" in marcas

    def test_parses_pattern_b(self, sample_boletin_text):
        """Pattern B: Insc. + NOMBRE DE LA MARCA."""
        parser = MarcaEntryParser()
        entries, stats = parser.parse_with_stats(sample_boletin_text)
        # Pattern B captura MARTINEZ INDUSTRIAL (NOMBRE DE LA MARCA explícito)
        assert stats.pattern_b_count >= 1
        marcas = {e.marca for e in entries if e.marca}
        assert "MARTINEZ INDUSTRIAL" in marcas

    def test_detects_lema_comercial(self, sample_boletin_text):
        """Entries con EN CLASE: LC se marcan como es_lema=True."""
        parser = MarcaEntryParser()
        entries, stats = parser.parse_with_stats(sample_boletin_text)
        assert stats.entries_lema >= 1
        lema_entries = [e for e in entries if e.es_lema]
        assert any(e.marca == "CALIDAD QUE NO SE OLVIDA" for e in lema_entries)
        assert all(e.clase_especial == "LC" for e in lema_entries)

    def test_asigna_estatus_de_seccion(self, sample_boletin_text):
        """Todas las entries del fixture deben tener estatus PUBLICADA."""
        parser = MarcaEntryParser(
            section_lookup=boletin_header.detect_current_section,
        )
        entries, _ = parser.parse_with_stats(sample_boletin_text)
        for e in entries:
            assert e.estatus == "PUBLICADA"

    def test_dedup_por_expediente(self):
        """Dos patterns que matcheen el mismo expediente → solo una entry."""
        text = (
            "Insc. 2026-001 del 01 DE ENERO DE 2026\n"
            "SOLICITADA POR: ACME S.A. Domicilio: X País: VENEZUELA\n"
            "ACME MARCA\n"
            "EN CLASE: 25\n"
            "NOMBRE DE LA MARCA: ACME MARCA\n"  # duplicado intencional
        )
        parser = MarcaEntryParser()
        entries = parser.parse(text)
        assert len(entries) == 1
        assert entries[0].expediente == "2026-001"

    def test_parse_text_without_entries(self):
        text = "Esta página no contiene entradas de marcas."
        parser = MarcaEntryParser()
        entries = parser.parse(text)
        assert entries == []

    def test_fecha_normalizada(self, sample_boletin_text):
        """Las fechas se normalizan a ISO 8601."""
        parser = MarcaEntryParser()
        entries = parser.parse(sample_boletin_text)
        # Buscar una entry con fecha
        with_fecha = [e for e in entries if e.fecha_inscripcion]
        assert len(with_fecha) >= 1
        assert all(e.fecha_inscripcion.startswith("20") for e in with_fecha)

    def test_pais_normalizado(self, sample_boletin_text):
        """Los países se limpian."""
        parser = MarcaEntryParser()
        entries = parser.parse(sample_boletin_text)
        with_pais = [e for e in entries if e.pais]
        # Al menos uno con país
        assert len(with_pais) >= 1

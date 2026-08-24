"""Tests de los parsers del boletín."""
from __future__ import annotations

from scripts.parsers import boletin_header, marca_entry


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


class TestMarcaEntry:
    def test_parse_multiple_entries(self, sample_pdf_text):
        entries = marca_entry.parse(sample_pdf_text)
        # Hay 5 entradas en el fixture
        assert len(entries) == 5

    def test_first_entry_expediente(self, sample_pdf_text):
        entries = marca_entry.parse(sample_pdf_text)
        first = entries[0]
        assert first.expediente == "2026-001234"
        assert first.marca == "ACME VENEZUELA"
        assert first.clase_niza == 25
        assert first.titular == "ACME HOLDINGS LLC"
        assert first.estatus == "CONCEDIDA"
        assert first.page == 1

    def test_entry_on_page_3(self, sample_pdf_text):
        entries = marca_entry.parse(sample_pdf_text)
        acme_textil = next(e for e in entries if "TEXTIL ACME" in e.marca)
        assert acme_textil.page == 3
        assert acme_textil.clase_niza == 24

    def test_parse_text_without_entries(self):
        text = "Esta página no contiene entradas de marcas."
        entries = marca_entry.parse(text)
        assert entries == []

    def test_marca_variants(self):
        text = (
            "--- página 1 ---\n"
            "Expediente: 2026-999\n"
            "Marca: ACME\n"
            "Clase: 25\n"
            "Titular: ACME S.A.\n"
            "Estatus: PUBLICADA\n"
        )
        entries = marca_entry.parse(text)
        assert len(entries) == 1
        assert entries[0].marca == "ACME"

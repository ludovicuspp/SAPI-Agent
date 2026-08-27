"""Tests de ``extract_page.py`` (texto por página + render a imagen)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract_page import page_text, page_low_confidence, render_page_png  # noqa: E402

SAMPLE_PDF = Path(__file__).resolve().parent.parent.parent.parent.parent / "tests" / "fixtures" / "sample_boletin.pdf"


@pytest.fixture()
def sample_pdf() -> Path:
    if not SAMPLE_PDF.exists():
        pytest.skip("No hay fixture sample_boletin.pdf")
    return SAMPLE_PDF


def test_page_text_extrae_texto(sample_pdf):
    text = page_text(sample_pdf, 1)
    assert isinstance(text, str)


def test_page_text_pagina_fuera_de_rango(sample_pdf):
    assert page_text(sample_pdf, 9999) == ""
    assert page_text(sample_pdf, 0) == ""


def test_page_low_confidence():
    assert page_low_confidence("poco") is True
    assert page_low_confidence("a" * 100) is False


def test_render_page_png_genera_archivo(sample_pdf, tmp_path):
    out = render_page_png(sample_pdf, 1, tmp_path)
    assert out is not None
    assert out.exists()
    assert out.suffix == ".png"
    assert out.stat().st_size > 0


def test_render_pagina_fuera_de_rango(sample_pdf, tmp_path):
    assert render_page_png(sample_pdf, 9999, tmp_path) is None

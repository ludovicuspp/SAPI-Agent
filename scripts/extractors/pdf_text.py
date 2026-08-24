"""Extractor de texto con pdfplumber."""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from scripts.extractors.base import ExtractionResult, PageExtract, is_low_confidence


def extract(pdf_path: Path) -> ExtractionResult:
    """Abre el PDF y extrae texto por página con pdfplumber.

    ``has_images`` se activa cuando pdfplumber reporta imágenes
    embebidas en la página. La extracción puede ser vacía si la
    página es escaneada (sólo imagen): en ese caso ``low_confidence``
    se activa y el processor marcará la página para revisión Hermes.
    """
    pages: list[PageExtract] = []
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            images = list(page.images)
            pages.append(
                PageExtract(
                    page_number=index,
                    text=text,
                    char_count=len(text),
                    has_images=len(images) > 0,
                    low_confidence=is_low_confidence(text),
                )
            )
    return ExtractionResult(pages=pages, total_pages=len(pages))

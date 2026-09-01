"""Extractor de texto con pdfplumber + fallback a pymupdf para cid:.

Cuando pdfplumber devuelve texto con caracteres ``(cid:NNN)`` (encoding
roto observado en BPI 654 con algunas versiones de pdfplumber),
se reintenta la extracción completa con pymupdf, que decodifica
correctamente esos casos.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import pdfplumber

from scripts.extractors.base import ExtractionResult, PageExtract, is_low_confidence


_CID_MARKER = "(cid:"


def _has_cid_encoding(pages: list[PageExtract]) -> bool:
    """Devuelve True si alguna página tiene caracteres cid: en su texto."""
    for page in pages:
        if _CID_MARKER in (page.text or ""):
            return True
    return False


def _extract_with_pdfplumber(
    pdf_path: Path,
    on_page: Optional[Callable[[int, int], None]] = None,
) -> list[PageExtract]:
    pages: list[PageExtract] = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
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
            if on_page is not None:
                on_page(index, total)
    return pages


def _extract_with_pymupdf(
    pdf_path: Path,
    on_page: Optional[Callable[[int, int], None]] = None,
) -> list[PageExtract]:
    import pymupdf

    pages: list[PageExtract] = []
    with pymupdf.open(str(pdf_path)) as doc:
        total = doc.page_count
        for index in range(total):
            page = doc[index]
            text = (page.get_text() or "").strip()
            images = page.get_images(full=True)
            pages.append(
                PageExtract(
                    page_number=index + 1,
                    text=text,
                    char_count=len(text),
                    has_images=len(images) > 0,
                    low_confidence=is_low_confidence(text),
                )
            )
            if on_page is not None:
                on_page(index + 1, total)
    return pages


def extract(
    pdf_path: Path,
    on_page: Optional[Callable[[int, int], None]] = None,
) -> ExtractionResult:
    """Abre el PDF y extrae texto por página.

    Estrategia: usa ``pdfplumber`` por defecto; si detecta ``(cid:NNN)``
    en alguna página (encoding corrupto), reintenta con ``pymupdf``
    para todo el documento.

    Si se pasa ``on_page(page_no, total)``, se invoca tras extraer cada
    página (1-indexed). Útil para reportar progreso.
    """
    pages = _extract_with_pdfplumber(pdf_path, on_page=on_page)
    if _has_cid_encoding(pages):
        pages = _extract_with_pymupdf(pdf_path, on_page=on_page)
    return ExtractionResult(pages=pages, total_pages=len(pages))

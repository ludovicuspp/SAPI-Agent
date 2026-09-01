"""Extractor de texto por lotes con gestión explícita de memoria.

Procesa el PDF en lotes de ``BATCH_SIZE`` páginas usando PyMuPDF
(menor consumo que pdfplumber). Cada página se libera explícitamente
(invocando ``gc.collect`` por defecto) tras extraer texto e imágenes,
evitando que el proceso acumule el documento completo en RAM.

Esto resuelve el OOM observado con boletines de 1000+ páginas (p.ej.
BPI 652: 1852 páginas llegaba a ~3.2 GB y el kernel lo eliminaba).

Dos modos:
  - ``extract_pdf_in_batches``: retiene ``ExtractionResult.pages``
    completo (para PDFs medianos / tests).
  - ``extract_pdf_in_batches_memory_efficient``: NO acumula páginas;
    la lógica de negocio la consume vía ``on_batch``. Ideal para el
    pipeline de producción con boletines masivos.
"""
from __future__ import annotations

import gc
from pathlib import Path
from typing import Callable, Optional

from scripts.extractors.base import ExtractionResult, PageExtract, is_low_confidence


BATCH_SIZE = 50


def _page_extract(page, page_number: int) -> PageExtract:
    text = (page.get_text() or "").strip()
    images = page.get_images(full=True)
    return PageExtract(
        page_number=page_number,
        text=text,
        char_count=len(text),
        has_images=len(images) > 0,
        low_confidence=is_low_confidence(text),
    )


def _has_cid(text: str) -> bool:
    return "(cid:" in text


def _iter_batches(
    pdf_path: Path,
    batch_size: int,
    *,
    start_page: int = 1,
    on_page: Optional[Callable[[int, int], None]],
    on_batch: Optional[Callable[[list[PageExtract], int, int], None]],
    collect: bool,
) -> tuple[int, bool, bool, bool]:
    """Itera el PDF por lotes invocando los callbacks.

    ``start_page`` (1-indexed, inclusive) permite reanudar desde un
    lote ya persistido sin reprocesar páginas previas.

    Retorna ``(total_pages, has_images, has_low_confidence, has_cid)``.
    """
    import pymupdf

    with pymupdf.open(str(pdf_path)) as doc:
        total = doc.page_count
        batch_pages: list[PageExtract] = []
        batch_start = start_page
        has_images = False
        has_low_conf = False
        has_cid = False

        for index in range(total):
            page_number = index + 1
            if page_number < start_page:
                continue
            page = doc[index]
            try:
                pe = _page_extract(page, page_number)
                if pe.has_images:
                    has_images = True
                if pe.low_confidence:
                    has_low_conf = True
                if _has_cid(pe.text or ""):
                    has_cid = True
                batch_pages.append(pe)
            finally:
                # Libera el objeto Page (mantiene refs internas al doc).
                page = None  # noqa: F841

            if on_page is not None:
                on_page(page_number, total)

            is_last = index == total - 1
            if len(batch_pages) >= batch_size or is_last:
                if on_batch is not None and batch_pages:
                    on_batch(batch_pages, batch_start, page_number)
                batch_pages = []
                batch_start = page_number + 1
                if collect:
                    gc.collect()

    return total, has_images, has_low_conf, has_cid


def extract_pdf_in_batches(
    pdf_path: Path,
    batch_size: int = BATCH_SIZE,
    *,
    start_page: int = 1,
    on_page: Optional[Callable[[int, int], None]] = None,
    on_batch: Optional[Callable[[list[PageExtract], int, int], None]] = None,
    collect: bool = True,
) -> ExtractionResult:
    """Extrae el PDF por lotes reteniendo todas las páginas en memoria.

    Útil para PDFs pequeños o en tests. Para boletines masivos usa
    ``extract_pdf_in_batches_memory_efficient``.
    """
    all_pages: list[PageExtract] = []

    def _batch(pages, start, end) -> None:
        all_pages.extend(pages)
        if on_batch is not None:
            on_batch(pages, start, end)

    total, _himg, _hlow, _hcid = _iter_batches(
        pdf_path,
        batch_size,
        start_page=start_page,
        on_page=on_page,
        on_batch=_batch,
        collect=collect,
    )
    return ExtractionResult(pages=all_pages, total_pages=total)


def extract_pdf_in_batches_memory_efficient(
    pdf_path: Path,
    batch_size: int = BATCH_SIZE,
    *,
    start_page: int = 1,
    on_page: Optional[Callable[[int, int], None]] = None,
    on_batch: Callable[[list[PageExtract], int, int], None],
    collect: bool = True,
) -> ExtractionResult:
    """Extrae el PDF por lotes SIN acumular el documento en memoria.

    ``on_batch`` es obligatoria: recibe cada lote y debe liberar
    las páginas cuando termine (retornar ``None`` y no guardarlas).
    """
    total, has_images, has_low_conf, has_cid = _iter_batches(
        pdf_path,
        batch_size,
        start_page=start_page,
        on_page=on_page,
        on_batch=on_batch,
        collect=collect,
    )
    # Nota: no conservamos has_images/has_cid en el resultado porque el
    # caller ya los observa por on_batch. Se exponen si fuesen necesarios.
    return ExtractionResult(pages=[], total_pages=total)

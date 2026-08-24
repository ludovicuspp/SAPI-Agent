"""Metadatos del PDF: hash, número de páginas, extracción de imágenes."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import pymupdf
from PIL import Image


def hash_file(path: Path) -> str:
    """SHA-256 hex del archivo en disco."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def count_pages(path: Path) -> int:
    """Número de páginas del PDF."""
    with pymupdf.open(str(path)) as doc:
        return doc.page_count


def render_page_to_image(
    pdf_path: Path,
    page_number: int,
    dpi: int = 200,
) -> Image.Image:
    """Renderiza una página del PDF a imagen PIL.

    Usado en Fase 5 por Hermes para alimentar al LLM multimodal con
    páginas escaneadas.
    """
    with pymupdf.open(str(pdf_path)) as doc:
        page = doc[page_number - 1]
        zoom = dpi / 72
        matrix = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        mode = "RGB"
        return Image.frombytes(mode, (pix.width, pix.height), pix.samples)

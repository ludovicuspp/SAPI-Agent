"""Tipos comunes de extracción.

Un ``PageExtract`` representa el resultado de extraer UNA página.
``has_images`` se activa cuando hay imágenes embebidas o cuando el
texto es prácticamente vacío (heurística que la API usa para
``needs_hermes_review``).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class PageExtract:
    page_number: int
    text: str
    char_count: int
    has_images: bool
    low_confidence: bool


@dataclass
class ExtractionResult:
    pages: list[PageExtract]
    total_pages: int


class Extractor(Protocol):
    """Interfaz para cualquier extractor de PDF."""

    def extract(self, pdf_path: Path) -> ExtractionResult: ...


def is_low_confidence(text: str) -> bool:
    """Heurística: < 50 caracteres visibles no es confiable."""
    visible = "".join(c for c in text if not c.isspace())
    return len(visible) < 50

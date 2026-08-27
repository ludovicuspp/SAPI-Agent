"""Extracción de una página concreta de un PDF a texto o a imagen.

La usa la skill cuando Hermes decide que una página requiere revisión
visual. Todo es lectura; no modifica el PDF ni la BD.

Uso (como archivo):
    python hermes/skills/sapi-monitor/scripts/extract_page.py --pdf X.pdf --page N
    python hermes/skills/sapi-monitor/scripts/extract_page.py --pdf X.pdf --page N --render OUT_DIR
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from _bootstrap import setup_paths

setup_paths()  # añade raíz del repo para importar scripts.extractors.base

import pdfplumber  # noqa: E402

from scripts.extractors.base import is_low_confidence  # noqa: E402


def page_text(pdf_path: str | Path, page_number: int) -> str:
    """Devuelve el texto de ``page_number`` (1-based).

    Usa pdfplumber y, si detecta caracteres ``(cid:NNN)``, reintenta con
    pymupdf, que decodifica mejor esos casos.
    """
    pdf_path = Path(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            return ""
        text = (pdf.pages[page_number - 1].extract_text() or "").strip()

    if "(cid:" in text:
        import pymupdf

        with pymupdf.open(str(pdf_path)) as doc:
            if page_number < 1 or page_number > doc.page_count:
                return ""
            text = (doc[page_number - 1].get_text() or "").strip()

    return text


def page_low_confidence(text: str) -> bool:
    """Reutiliza la heurística del repo: < 50 caracteres visibles."""
    return is_low_confidence(text)


def render_page_png(
    pdf_path: str | Path, page_number: int, out_dir: str | Path, dpi: int = 150
) -> Optional[Path]:
    """Renderiza ``page_number`` a PNG y lo guarda en ``out_dir``.

    Devuelve la ruta del PNG generado o ``None`` si la página no existe.
    Requiere ``pymupdf``.
    """
    import pymupdf

    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with pymupdf.open(str(pdf_path)) as doc:
        if page_number < 1 or page_number > doc.page_count:
            return None
        page = doc[page_number - 1]
        zoom = dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        out_path = out_dir / f"page_{page_number:04d}.png"
        pix.save(str(out_path))
        return out_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Extrae texto o renderiza a PNG una página de un PDF SAPI."
    )
    parser.add_argument("--pdf", required=True, help="Ruta al PDF")
    parser.add_argument("--page", required=True, type=int, help="Nº de página (1-based)")
    parser.add_argument("--render", help="Directorio destino PNG (activar render en vez de texto)")
    parser.add_argument("--dpi", type=int, default=150, help="DPI del render (default 150)")
    args = parser.parse_args(argv)

    if args.render:
        out = render_page_png(args.pdf, args.page, args.render, dpi=args.dpi)
        if out is None:
            print(f"Página {args.page} no existe en {args.pdf}")
        else:
            print(f"Renderizado: {out}")
        return

    text = page_text(args.pdf, args.page)
    print(text)
    print(f"// confianza_baja={page_low_confidence(text)}")


if __name__ == "__main__":
    main()

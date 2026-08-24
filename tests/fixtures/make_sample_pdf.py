"""Genera un PDF de boletín sintético para tests de integración.

Uso::

    python tests/fixtures/make_sample_pdf.py [salida.pdf]
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


TEXT = """REPÚBLICA BOLIVARIANA DE VENEZUELA
MINISTERIO DEL PODER POPULAR DE INDUSTRIAS Y COMERCIO NACIONAL

Boletín N° 651 — Caracas, martes 10 de marzo de 2026 — Tomo IX

Página 1

SOLICITUDES DE MARCAS DE PRODUCTOS CONCEDIDAS

Expediente: 2026-001234
Marca: ACME VENEZUELA
Clase: 25
Titular: ACME HOLDINGS LLC
Estatus: CONCEDIDA

Expediente: 2026-001235
Marca: MARTINEZ Y ASOCIADOS
Clase: 35
Titular: MARTINEZ & ASOCIADOS C.A.
Estatus: PUBLICADA

Página 2

Expediente: 2026-001236
Marca: GLOBAL TECH SOLUTIONS
Clase: 42
Titular: GLOBAL TECH HOLDINGS
Estatus: CONCEDIDA

Expediente: 2026-001237
Marca: TECNO MART
Clase: 9
Titular: COMERCIAL MARTINEZ C.A.
Estatus: PUBLICADA

Página 3

Expediente: 2026-001238
Marca: TEXTIL ACME
Clase: 24
Titular: TEXTILERIA ACME S.A.
Estatus: PUBLICADA
"""


def main(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=letter)
    width, height = letter
    y = height - 50
    lines = TEXT.splitlines()
    page_breaks = {"Página 1", "Página 2", "Página 3"}
    for line in lines:
        if line in page_breaks:
            c.showPage()
            y = height - 50
            continue
        c.drawString(50, y, line)
        y -= 16
    c.save()
    print(f"PDF de prueba escrito en {output}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_boletin.pdf")
    main(out)

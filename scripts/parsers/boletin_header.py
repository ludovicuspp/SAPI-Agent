"""Auto-detección de metadatos del boletín desde el texto.

Estrategia: regex tolerantes a mayúsculas/minúsculas y a las
variantes observadas en boletines reales de SAPI (``Boletín N° 651``,
``BOLETIN 651``, ``Boletin Nº 651``, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class BoletinMetadata:
    bulletin_number: int | None = None
    period: str | None = None
    tomo: str | None = None
    raw_matches: dict[str, str] = field(default_factory=dict)


_BULLETIN_RE = re.compile(
    r"[Bb]olet[íi]n\s*(?:N[°ºo.]?|N\.?|N°|Nro\.?)?\s*(\d+)",
    re.IGNORECASE,
)

_PERIOD_RE = re.compile(
    r"Caracas,\s+\w+\s+\d{1,2}\s+de\s+(\w+)\s+de\s+(\d{4})",
    re.IGNORECASE,
)

_TOMO_RE = re.compile(
    r"[Tt]omo[s]?\s*[:.]?\s*([IVXLCDM]+(?:[/-][IVXLCDM]+)?)",
    re.IGNORECASE,
)


_MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def detect(text: str) -> BoletinMetadata:
    """Detecta número, período y tomo del boletín a partir del texto."""
    md = BoletinMetadata()

    m = _BULLETIN_RE.search(text)
    if m:
        try:
            md.bulletin_number = int(m.group(1))
            md.raw_matches["bulletin_number"] = m.group(0)
        except ValueError:
            pass

    m = _PERIOD_RE.search(text)
    if m:
        month_name = m.group(1).lower()
        year = m.group(2)
        month = _MONTHS_ES.get(month_name, 0)
        if month:
            md.period = f"{year}-{month:02d} ({month_name.capitalize()} {year})"
            md.raw_matches["period"] = m.group(0)

    m = _TOMO_RE.search(text)
    if m:
        md.tomo = m.group(1).upper()
        md.raw_matches["tomo"] = m.group(0)

    return md

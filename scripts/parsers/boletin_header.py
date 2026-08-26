"""Auto-detección de metadatos del boletín desde el texto.

Estrategia: regex tolerantes a mayúsculas/minúsculas y a las
variantes observadas en boletines reales de SAPI (``Boletín N° 651``,
``BOLETIN 651``, ``Boletin Nº 651``, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Catálogo de secciones observadas en BPI 651-655 ─────────────


SECCIONES: dict[str, str | None] = {
    # Marcas
    "MARCAS CON ORDEN DE PUBLICACIÓN EN PRENSA": "PUBLICADA",
    "MARCAS CON ORDEN DE PUBLICACIÓN": "PUBLICADA",
    "MARCAS DE PRODUCTOS CONCEDIDAS": "CONCEDIDA",
    "MARCAS DE SERVICIOS CONCEDIDAS": "CONCEDIDA",
    "MARCAS NEGADAS": "NEGADA",
    "MARCAS CADUCAS POR NO PAGO DE DERECHO": "CADUCA",
    "MARCAS CADUCAS POR NO PAGO": "CADUCA",
    "MARCAS DESISTIDAS": "DESISTIDA",
    "RENOVACIONES DE MARCAS Y OTROS": "RENOVADA",
    "RENOVACIONES DE MARCAS": "RENOVADA",
    "SOLICITUDES DE MARCAS DE PRODUCTOS DEVUELTAS": "DEVUELTA",
    "SOLICITUDES DE MARCAS DE SERVICIOS DEVUELTAS": "DEVUELTA",
    "OPOSICIONES": "OPOSICION",
    # Nombres comerciales
    "NOMBRES COMERCIALES CONCEDIDAS": "CONCEDIDA",
    "NOMBRES COMERCIALES": "CONCEDIDA",
    # Lemas comerciales
    "LEMAS COMERCIALES CONCEDIDOS": "CONCEDIDA",
    "LEMAS COMERCIALES CONCEDIDAS": "CONCEDIDA",
    # Administrativas (no son marcas en sí)
    "DISPOSICIONES ADMINISTRATIVAS": None,
    "CESIONES DE MARCAS Y OTROS SIGNOS DISTINTIVOS": "CESION",
    "FUSIONES DE MARCAS Y OTROS SIGNOS DISTINTIVOS": "FUSION",
    "LICENCIAS DE USO DE MARCA": "LICENCIA",
    "CAMBIO DE NOMBRE DE MARCAS Y OTROS SIGNOS DISTINTIVOS": "CAMBIO_NOMBRE",
    "CAMBIO DE DOMICILIO DE MARCAS Y OTROS SIGNOS DISTINTIVOS": "CAMBIO_DOMICILIO",
}


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
    r"[Tt]omos?\s*[:.]?\s*([IVXLCDM]+(?:[/-][IVXLCDM]+)?)",
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


# ── Detección inline de sección actual ────────────────────────


# Pre-compilamos las regex de las secciones (case-insensitive, palabra completa).
_SECCION_PATTERNS = [
    (re.compile(re.escape(kw), re.IGNORECASE), estatus)
    for kw, estatus in SECCIONES.items()
]


def detect_current_section(text: str, position: int) -> str | None:
    """Devuelve el estatus de la última sección detectada antes de ``position``.

    Si no hay sección reconocible, devuelve ``None``.
    """
    best_pos = -1
    best_estatus: str | None = None
    head = text[: max(0, position)]
    for pat, estatus in _SECCION_PATTERNS:
        for m in pat.finditer(head):
            if m.start() > best_pos:
                best_pos = m.start()
                best_estatus = estatus
    return best_estatus

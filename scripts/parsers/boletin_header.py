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
    # Variantes reales observadas en BPI 654 (secciones cortas).
    "DEVUELTAS DE FORMA": "DEVUELTA",
    "DEVUELTAS DE FONDO": "DEVUELTA",
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
    fecha_publicacion: str | None = None
    raw_matches: dict[str, str] = field(default_factory=dict)


_BULLETIN_RE = re.compile(
    r"[Bb]olet[íi]n\s*(?:N[°ºo.]?|N\.?|N°|Nro\.?)?\s*(\d+)",
    re.IGNORECASE,
)

_PERIOD_RE = re.compile(
    r"Caracas,\s*\w+,?\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
    re.IGNORECASE,
)

_TOMO_RE = re.compile(
    r"[Tt]omos?\s*[:.]?\s*([IVXLCDM]+(?:[/-][IVXLCDM]+)?)",
    re.IGNORECASE,
)

# Cabecera de inicio de tomo: "Tomo 02/18", "Tomo 9 / 22", etc. Solo
# aparece en la primera página de cada tomo y es la señal más fiable para
# dividir el PDF en rangos de páginas → tomo.
_TOMO_START_RE = re.compile(r"[Tt]omo\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)


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
        month_name = m.group(2).lower()
        year = m.group(3)
        month = _MONTHS_ES.get(month_name, 0)
        if month:
            md.period = f"{year}-{month:02d} ({month_name.capitalize()} {year})"
            md.fecha_publicacion = f"{year}-{month:02d}-{int(m.group(1)):02d}"
            md.raw_matches["period"] = m.group(0)
            md.raw_matches["fecha_publicacion"] = md.fecha_publicacion

    m = _TOMO_RE.search(text)
    if m:
        md.tomo = m.group(1).upper()
        md.raw_matches["tomo"] = m.group(0)

    return md


# ── Tomos por rango de páginas ───────────────────────────────


def _arabic_to_roman(n: int) -> str:
    """Convierte 1..3999 a numerales romanos (para el tomo)."""
    if n < 1:
        return str(n)
    vals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    out = []
    for value, symbol in vals:
        while n >= value:
            out.append(symbol)
            n -= value
    return "".join(out)


def tomo_ranges(text: str) -> list[tuple[int, int, int]]:
    """Divide el boletín en tomos según sus cabeceras de inicio.

    Busca las ocurrencias de ``Tomo N/TOTAL`` (p.ej. ``Tomo 02/18``) y
    devuelve una lista de ``(page_inicio, tomo_arabico, total_tomos)``
    ordenada por página. La primera página de un tomo suele ser N=1
    (página 1) seguida del resto; se devuelve una entrada por cabecera
    detectada (sin dedup por número repetido en el mismo rango).
    """
    ranges: list[tuple[int, int, int, int]] = []
    for m in _TOMO_START_RE.finditer(text):
        num = int(m.group(1))
        total = int(m.group(2))
        page = _page_of(text, m.start())
        ranges.append((page, num, total, m.start()))
    # Deducir las páginas de inicio de manera robusta: la posición del
    # match ya indica dónde empieza; _page_of lo resuelve si hay página.
    return [(p, n, t) for p, n, t, _ in ranges]


def _page_of(text: str, position: int) -> int:
    """Devuelve el número de página del marcador ``--- página N ---``
    inmediatamente anterior a ``position``."""
    page_re = re.compile(r"--- página (\d+) ---")
    best = -1
    best_page = 0
    for m in page_re.finditer(text):
        if m.start() <= position:
            best = m.start()
            best_page = int(m.group(1))
    return best_page


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


# ── Tipo de disposición implícito en la sección ────────────────

# Algunas secciones implican de por sí un tipo de disposición
# administrativa (p.ej. la distinción devolución de forma vs fondo).
# Valores del conjunto cerrado ``DisposicionTipoLiteral`` en
# ``scripts/schemas.py``.
DISPOSICION_POR_SECCION: dict[str, str] = {
    "DEVUELTAS DE FORMA": "DEVOLUCION_FORMA",
    "DEVUELTAS DE FONDO": "DEVOLUCION_FONDO",
    "SOLICITUDES DE MARCAS DE PRODUCTOS DEVUELTAS": "DEVOLUCION_FORMA",
    "SOLICITUDES DE MARCAS DE SERVICIOS DEVUELTAS": "DEVOLUCION_FORMA",
}

_DISPOSICION_PATTERNS = [
    (re.compile(re.escape(kw), re.IGNORECASE), tipo)
    for kw, tipo in DISPOSICION_POR_SECCION.items()
]


def detect_current_disposicion(text: str, position: int) -> str | None:
    """Devuelve el tipo de disposición de la última sección que implica
    alguna, antes de ``position``. ``None`` si la sección no implica una.

    Complementa a ``detect_current_section``: las secciones de devoluciones
    distinguen forma vs fondo sin inventar estatus nuevos.
    """
    best_pos = -1
    best_tipo: str | None = None
    head = text[: max(0, position)]
    for pat, tipo in _DISPOSICION_PATTERNS:
        for m in pat.finditer(head):
            if m.start() > best_pos:
                best_pos = m.start()
                best_tipo = tipo
    return best_tipo

"""Patterns comunes y utilidades de limpieza/normalización.

Funciones de limpieza transversales para los datos crudos extraídos
del boletín. Aplican reglas observadas en BPI 651-655.
"""
from __future__ import annotations

import re
from typing import Optional


# ── Regex transversales ────────────────────────────────────────

# `H PIMACO`, `N SERVICENOW`, `E LA GEAR`, `C FRESH FOOD`, `Z …`
# Caracteres de control de maquetación al inicio de una línea.
CHARSET_PREFIX_RE = re.compile(r"^[HNECZ]\s+")

# Traducción entre paréntesis: "EXTREMEN FLOTATION (FLOTACIÓN EXTREMA)"
TRANSLATION_PAREN_RE = re.compile(r"\s*\(([^)]+)\)\s*$")

# `Insc. AAAA-NNNNNN` (inscripción / expediente SAPI). El expediente
# puede tener entre 3 y 7 dígitos después del guion (ej. ``2026-001`` o
# ``2016-013049``).
INSC_RE = re.compile(
    r"Insc\.\s*(?P<expediente>\d{4}-\d{3,7})\s+del\s+"
    r"(?P<fecha>\d{1,2}\s+DE\s+\w+\s+DE\s+\d{4})",
    re.IGNORECASE,
)

# `SOLICITADA POR:` o variantes con/sin espacio, con/sin salto de línea.
SOLICITADA_RE = re.compile(
    r"SOLICITADA\s*POR:?\s*\n?\s*"
    r"(?P<titular>[^\n]+?)(?=\s+Domicilio|\s+Pa[íi]s|$)",
    re.IGNORECASE | re.MULTILINE,
)

# `EN CLASE: NN`, `Clase NN`, o `EN CLASE: LC` (lema comercial), con
# espacios flexibles. Algunas entradas del boletín escriben la clase
# sin el prefijo "EN" (p.ej. "Clase 39") al final del bloque de
# "PARA DISTINGUIR".
CLASE_RE = re.compile(
    r"(?:EN\s+)?CLASE\s*:?\s*(?P<clase>\d{1,2}|LC)\b",
    re.IGNORECASE,
)

# `PARA DISTINGUIR: <descripción>` (productos/servicios). Corta al primer
# salto de línea y limpia ruido de maquetación.
DISTINGUIR_RE = re.compile(
    r"PARA\s+DISTINGUIR\s*:\s*(?P<distinguir>[^\n]+)",
    re.IGNORECASE,
)

# `País: <nombre>` con tolerancia a saltos de línea.
PAIS_RE = re.compile(
    r"Pa[íi]s\s*:?\s*(?P<pais>[^\n]+?)(?=\s+EN\s+CLASE|"
    r"\n[A-Z][A-Z0-9\s\-\.&©´']{3,}|\n\n|$)",
    re.IGNORECASE,
)

# `NOMBRE DE LA MARCA: <marca>` (patrón B).
NOMBRE_MARCA_RE = re.compile(
    r"NOMBRE DE LA MARCA\s*:\s*(?P<marca>[^\n]+)",
    re.IGNORECASE,
)

# Marcador de sección con marca figurativa.
DESCRIPCION_ETIQUETA_RE = re.compile(
    r"DESCRIPCION DE ETIQUETA", re.IGNORECASE,
)

# Meses en español para normalización de fechas.
MONTHS_ES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9,
    "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


# ── Limpieza ───────────────────────────────────────────────────


def clean_text(value: Optional[str]) -> Optional[str]:
    """Limpia espacios redundantes. ``None`` se preserva."""
    if value is None:
        return None
    return " ".join(value.split())


def is_upperish(s: str, threshold: float = 0.7) -> bool:
    """``True`` si al menos ``threshold`` de las letras alfabéticas
    son mayúsculas. Útil para detectar líneas de marca denominativa."""
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= threshold


def clean_marca(raw: Optional[str]) -> Optional[str]:
    """Limpia el nombre de la marca: quita prefijo H/N/E/C/Z y
    la traducción entre paréntesis al final.

    ``"H PIMACO"`` → ``"PIMACO"``
    ``"EXTREMEN FLOTATION (FLOTACIÓN EXTREMA)"`` → ``"EXTREMEN FLOTATION"``
    ``"N SERVICENOW"`` → ``"SERVICENOW"``
    Preserva caracteres válidos: ``©``, ``´``, ``.``, números, ``&``, ``-``, ``'``.
    """
    if raw is None:
        return None
    s = raw.strip()
    s = CHARSET_PREFIX_RE.sub("", s, count=1)
    if TRANSLATION_PAREN_RE.search(s):
        s = TRANSLATION_PAREN_RE.sub("", s)
    return " ".join(s.split()).rstrip(" ,;.-")


def clean_titular(raw: Optional[str]) -> Optional[str]:
    """Limpia el titular: quita domicilio/país/tramitante que se hayan
    pegado por salto de línea o espacios faltantes.

    ``"MILKAUT S.A Domicilio: ARGENTINA,BUENOS AIRES,..."``
        → ``"MILKAUT S.A"``
    ``"UCAMAY CORP, C.A.\\n Domicilio: ..."`` → ``"UCAMAY CORP, C.A."``
    """
    if raw is None:
        return None
    s = raw.strip()
    # Cortar antes de palabras clave que no son parte del titular.
    for kw in ("Domicilio:", "País:", "TRAMITANTE:", "EN CLASE:", "PARA DISTINGUIR:"):
        idx = s.lower().find(kw.lower())
        if idx > 0:
            s = s[:idx]
    s = " ".join(s.split())
    return s.rstrip(" ,;.-")


def normalize_pais(raw: Optional[str]) -> Optional[str]:
    """Limpia y normaliza el país.

    ``"ESTADOS UNIDOSDEAMÉRICA"`` → ``"ESTADOS UNIDOS DE AMÉRICA"``
    ``"VENEZUELA"`` → ``"VENEZUELA"``
    Quita ``(cid:NNN)`` residual.

    Estrategia: insertar espacio antes de palabras comunes (DE, DEL,
    LA, LAS, EL, LOS, Y, EN) que aparezcan **entre** dos secuencias de
    mayúsculas. No aplica dentro de una sola palabra (ej. VENEZUELA).
    """
    if raw is None:
        return None
    s = raw.strip()
    # Quitar cid: residuales primero.
    s = re.sub(r"\(cid:\d+\)", " ", s)
    for _ in range(5):
        new_s = s
        # Caso "MAYUSCULAS{DEL,DE,LA,etc}MAYUSCULA" donde hay 2+ chars
        # en mayúsculas antes de la palabra conocida. NO aplica si la
        # palabra conocida está en medio de una palabra corta
        # (ej. "EL" dentro de "VENEZUELA": V-E-N-E-Z-U-EL-A).
        new_s = re.sub(
            r"([A-ZÁÉÍÓÚÑ]{2,})(DEL|DE|LA|LAS|EL|LOS|Y|EN)([A-ZÁÉÍÓÚÑ]{2,})",
            r"\1 \2 \3", new_s,
        )
        # minúscula→mayúscula (palabra pegada a la anterior)
        new_s = re.sub(r"([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])", r"\1 \2", new_s)
        if new_s == s:
            break
        s = new_s
    s = " ".join(s.split())
    return s.rstrip(" ,;.-")


def normalize_fecha(raw: Optional[str]) -> Optional[str]:
    """Normaliza la fecha en español a ISO.

    ``"30 DE OCTUBRE DE 2015"`` → ``"2015-10-30"``
    ``None`` o formato irreconocible → ``None``.
    """
    if raw is None:
        return None
    m = re.match(
        r"(\d{1,2})\s+DE\s+(\w+)\s+DE\s+(\d{4})", raw, re.IGNORECASE,
    )
    if not m:
        return None
    day_s, month_name, year_s = m.groups()
    month = MONTHS_ES.get(month_name.upper())
    if not month:
        return None
    try:
        day = int(day_s)
        year = int(year_s)
    except ValueError:
        return None
    if not (1 <= day <= 31) or not (1900 <= year <= 2100):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_clase(raw: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """Parsea el campo ``EN CLASE``.

    ``"30"`` → ``(30, None)``
    ``"LC"`` → ``(None, "LC")`` (lema comercial)
    ``None`` → ``(None, None)``
    """
    if raw is None:
        return None, None
    raw_up = raw.strip().upper()
    if raw_up == "LC":
        return None, "LC"
    try:
        n = int(raw_up)
        if 1 <= n <= 45:
            return n, None
    except ValueError:
        pass
    return None, None


# ── Detección de líneas de marca ───────────────────────────────


# Palabras que nunca son parte de una marca denominativa.
_BRAND_BLOCKLIST = (
    "PARA DISTINGUIR", "TRAMITANTE", "DESCRIPCION", "EN CLASE",
    "SOLICITADA POR", "DOMICILIO", "PAIS", "PAÍS", "INSCR",
    "NOMBRES", "LEMAS", "MARCAS", "REGISTRADOR", "RESOLUCIÓN",
)


def extract_brand_lines(text: str, start: int = 0, end: int | None = None) -> list[str]:
    """Devuelve las líneas consecutivas en MAYÚSCULAS (≥70%) que podrían
    ser el nombre de una marca. Hasta 3 líneas. Excluye líneas en blocklist.

    ``text[start:end]`` es el segmento a inspeccionar (entre País y EN CLASE).
    """
    if end is None:
        end = len(text)
    segment = text[start:end]
    lines = []
    for raw_line in segment.split("\n"):
        line = raw_line.strip()
        if not line:
            if lines:
                break  # línea vacía termina la marca multi-línea
            continue
        # Ignorar líneas en blocklist.
        if any(line.upper().startswith(b) for b in _BRAND_BLOCKLIST):
            break
        # Ignorar líneas que son claramente Domicilio/País residuales.
        if line.upper().startswith(("DOMICILIO", "PAÍS", "PAIS")):
            break
        # Aceptar línea si es MAYÚSCULAS, longitud ≥3, y no es metadata.
        if len(line) >= 3 and is_upperish(line, 0.7):
            lines.append(line)
            if len(lines) >= 3:
                break
        else:
            break  # línea que no es marca: terminamos
    return lines

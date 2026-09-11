"""Extracción del plazo legal (días hábiles) directamente del boletín SAPI.

El propio boletín publica el plazo en dos sitios:
  1. Cabecera de la sección: ``"...DENTRO DE UN LAPSO DE TREINTA (30) DÍAS
     HÁBILES CONTADOS A PARTIR DE LA FECHA DE LA PUBLICACIÓN..."``.
  2. Texto completo de los artículos de la LPI que el boletin reimprime
     (arts. 77–83): ``"...dentro del plazo de quince días hábiles..."``.

Si una entrada tiene ``disposicion`` con un plazo explícito, lo extraemos.
Si la sección publica un plazo genérico en su cabecera, lo aplicamos a
las entradas que comparten el mismo encabezado de sección hasta el
siguiente corte.

Devuelve:
  - ``dias``: int (días hábiles; si el texto dice "días" sin "hábiles"
    se asume hábiles también porque así lo usa SAPI en este boletín).
  - ``source``: cómo se obtuvo ('regex_disposicion', 'regex_seccion',
    'fallback_lpi').
"""
from __future__ import annotations

import re
from typing import Optional

# "TREINTA (30) DÍAS HÁBILES" / "treinta (30) días hábiles"
_RE_NHAB = re.compile(
    r"\b("
    r"un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|"
    r"trece|catorce|quince|dieciséis|dieciseis|diecisiete|dieciocho|"
    r"diecinueve|veinte|veinti[úu]n|veintid[óo]s|veintitr[ée]s|"
    r"veinticuatro|veinticinco|veintiséis|veintiseis|veintisiete|"
    r"veintiocho|veintinueve|treinta|treinta y un|treinta y uno|"
    r"cuarenta|cincuenta|sesenta|setenta|ochenta|noventa"
    r")\s*\(?(\d{1,3})\)?\s*d[ií]as?\s*(?:h[aá]biles|calendario|h[áa]bil)\b",
    re.IGNORECASE,
)

# Numérico simple: "diez días", "30 días", "diez (10) días", "(10) días"
_RE_NUM = re.compile(
    r"\b(\d{1,3})\)?\s*d[ií]as?\b",
    re.IGNORECASE,
)


def _to_int(token_num: int | str) -> Optional[int]:
    """Normaliza la cifra (entera) encontrada."""
    try:
        n = int(token_num)
    except (TypeError, ValueError):
        return None
    if 1 <= n <= 365:
        return n
    return None


def parse_lapse_from_text(text: Optional[str]) -> Optional[int]:
    """Devuelve el primer plazo explícito (días hábiles o naturales)
    mencionado en ``text`` o ``None`` si no hay.
    """
    if not text:
        return None
    m = _RE_NHAB.search(text)
    if m:
        return _to_int(m.group(2))
    m = _RE_NUM.search(text)
    if m:
        return _to_int(m.group(1))
    return None


def lapse_for_entry(
    disposicion: Optional[str],
    section_header: Optional[str] = None,
    *,
    fallback_lpi: Optional[int] = None,
) -> tuple[Optional[int], str]:
    """Devuelve ``(dias, source)`` para una entrada.

    Prioridad:
      1. Plazo en la disposicion concreta (regex).
      2. Plazo en la cabecera de sección (regex, si se pasa).
      3. Fallback legal publicado por SAPI en el boletín (LPI/LOPA).
    """
    d = parse_lapse_from_text(disposicion)
    if d is not None:
        return d, "regex_disposicion"
    if section_header:
        s = parse_lapse_from_text(section_header)
        if s is not None:
            return s, "regex_seccion"
    if fallback_lpi is not None:
        return fallback_lpi, "fallback_lpi"
    return None, "none"
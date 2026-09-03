"""Tokenización y comparación del campo ``PARA DISTINGUIR`` (productos/servicios).

La watchlist del usuario puede llevar el campo ``productos_servicios``
que define qué productos/servicios quiere vigilar. La entry del boletín
también lo trae (extraído por el parser). Para considerarlos compatibles
se tokenizan ambos textos, se filtran stopwords y se exige intersección
mínima de tokens significativos.

Si alguno de los dos textos está ausente, la función ``products_intersect``
devuelve ``None`` (el llamador decide el fallback — p.ej. continuar el
match solo con nombre + clase Niza).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional


# Stopwords en español + conectores típicos de boletines SAPI.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "al", "algo", "algunas", "algunos", "ante", "antes",
        "como", "con", "contra", "cual", "cuando", "de", "del",
        "desde", "donde", "durante", "e", "el", "ella", "ellas",
        "ellos", "en", "entre", "era", "eran", "es", "esa", "esas",
        "ese", "eso", "esos", "esta", "estar", "estas", "este",
        "esto", "estos", "estuvo", "fue", "fueron", "ha", "haber",
        "había", "han", "hasta", "hay", "la", "las", "le", "les",
        "lo", "los", "más", "mas", "mediante", "muy", "nada",
        "ni", "no", "nos", "nosotros", "nuestra", "nuestras",
        "nuestro", "nuestros", "o", "os", "otra", "otras", "otro",
        "otros", "para", "pero", "poco", "por", "porque", "que",
        "quien", "quienes", "se", "sea", "sean", "seas", "ser",
        "será", "serán", "si", "sido", "siempre", "siendo", "sin",
        "sobre", "sois", "somos", "son", "soy", "su", "sus",
        "también", "tan", "tanto", "te", "tendrá", "tendrán",
        "tenido", "teniendo", "tiempo", "tiene", "tienen", "todo",
        "todos", "tras", "tu", "tus", "un", "una", "unas", "uno",
        "unos", "vosotros", "vuestra", "vuestras", "vuestro",
        "vuestros", "y", "ya",
        # Términos que SAPI repite y no aportan semántica de producto.
        "distingue", "distinguir", "incluyendo", "principalmente",
        "servicios", "servicio", "productos", "producto", "todos",
        "todo", "clase",
    }
)

_TOKEN_RE = re.compile(r"[a-záéíóúñü0-9]{3,}")


def _strip_accents(s: str) -> str:
    """Quita acentos para colapsar variantes ortográficas."""
    import unicodedata

    return "".join(
        c
        for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def tokenize_distinguish(text: Optional[str]) -> set[str]:
    """Tokens significativos de un texto ``PARA DISTINGUIR``.

    - Normaliza a minúsculas y sin acentos.
    - Mantiene solo palabras alfanuméricas de longitud ≥3.
    - Filtra stopwords (español + términos del boletín).
    """
    if not text:
        return set()
    norm = _strip_accents(text.lower())
    tokens: set[str] = set()
    for tok in _TOKEN_RE.findall(norm):
        if tok in _STOPWORDS:
            continue
        tokens.add(tok)
    return tokens


def products_intersect(
    a: Optional[str], b: Optional[str], min_overlap: int = 1
) -> Optional[bool]:
    """Devuelve ``True`` si los productos comparten al menos ``min_overlap``
    tokens significativos, ``False`` si comparten menos.

    Si alguno de los dos textos está vacío/ausente, devuelve ``None``
    para que el llamador decida el fallback (p.ej. aceptar el match
    solo por nombre + clase).
    """
    ta = tokenize_distinguish(a)
    tb = tokenize_distinguish(b)
    if not ta or not tb:
        return None
    overlap = len(ta & tb)
    return overlap >= min_overlap

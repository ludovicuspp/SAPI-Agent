"""Normalización y coincidencia exacta (case-insensitive, sin acentos)."""
from __future__ import annotations

import unicodedata


def normalize(value: str) -> str:
    """Minúsculas + sin diacríticos + colapsa espacios.

    ``MARTÍNEZ`` → ``martinez``. ``  ÁCme  VENEZUELA  `` → ``acme venezuela``.
    """
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(without_marks.lower().split())


def exact_score(a: str, b: str) -> float:
    """1.0 si ``normalize(a) == normalize(b)``, si no 0.0."""
    return 1.0 if normalize(a) == normalize(b) and bool(normalize(a)) else 0.0

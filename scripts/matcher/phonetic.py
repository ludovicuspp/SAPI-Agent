"""Coincidencia fonética con jellyfish.metaphone.

Limitación conocida: metaphone está optimizado para inglés. Para
español captura aproximaciones obvias (MARTINEZ/MARTINES) pero no
reglas fonéticas castellanas. Documentado en ``docs/limitaciones.md``
cuando se escriba en Fase 6.
"""
from __future__ import annotations

import jellyfish

from scripts.matcher.exact import normalize


def phonetic_code(value: str) -> str:
    """Devuelve el código metaphone del valor normalizado."""
    return jellyfish.metaphone(normalize(value))


def phonetic_score(a: str, b: str) -> float:
    """1.0 si comparten código metaphone y el código no está vacío."""
    ca, cb = phonetic_code(a), phonetic_code(b)
    if not ca or not cb:
        return 0.0
    return 1.0 if ca == cb else 0.0

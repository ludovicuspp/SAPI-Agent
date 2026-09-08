"""Coincidencia fonética con jellyfish.metaphone.

Metaphone está optimizado para inglés; para español aplicamos una
normalización hispana previa que colapsa variantes fonéticas comunes:

- ``k``/``qu``/``c(e,i)`` → ``k`` (KWIK/QUICK, KIOSKO/QUIOSCO)
- ``z``/``c(e,i)`` → ``s`` (ZAPATO/SAPATO, CERO/SERO)
- ``v``/``b`` → ``b`` (BACA/VACA, BOLIVAR/VOLIBAR)
- ``h`` muda fuera (HECHO/ECHO)
- ``ll`` → ``y`` (LLAVE/YAVE), ``ñ`` → ``n`` (NIÑO/NINO)

La normalización es solo para el código fonético (no se guarda en BD).
"""
from __future__ import annotations

import re
import unicodedata

import jellyfish

from scripts.matcher.exact import normalize


def _hispano(text: str) -> str:
    """Aplica transformaciones hispanas sobre el texto normalizado."""
    t = normalize(text)
    if not t:
        return ""
    # Dígrafos antes de letras simples.
    t = t.replace("ll", "y")
    t = t.replace("ñ", "n")
    # H muda (no tras c: 'ch' se conserva para metaphone).
    t = re.sub(r"(?<![c])h", "", t)
    # qu -> k y q suelta -> k.
    t = t.replace("qu", "k").replace("q", "k")
    # z -> s, v -> b.
    t = t.replace("z", "s").replace("v", "b")
    # c+e/i -> s, resto de c -> k.
    t = re.sub(r"c(?=[ei])", "s", t).replace("c", "k")
    return t


def phonetic_code(value: str) -> str:
    """Devuelve el código metaphone del valor normalizado con fonética hispana."""
    return jellyfish.metaphone(_hispano(value))


def phonetic_score(a: str, b: str) -> float:
    """1.0 si comparten código metaphone (hispano) y el código no está vacío."""
    ca, cb = phonetic_code(a), phonetic_code(b)
    if not ca or not cb:
        return 0.0
    return 1.0 if ca == cb else 0.0
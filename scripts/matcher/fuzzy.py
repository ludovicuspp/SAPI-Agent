"""Coincidencia difusa con rapidfuzz."""
from __future__ import annotations

from rapidfuzz import fuzz

from scripts.matcher.exact import normalize


def fuzzy_score(a: str, b: str) -> float:
    """Score combinado (0.0–1.0) usando ``token_set_ratio`` + ``WRatio``.

    ``token_set_ratio`` ignora orden y duplicados de tokens; ``WRatio``
    es el agregado "inteligente" de rapidfuzz. Devolvemos el mejor de
    ambos para cubrir tanto reordenamientos como typos pequeños.
    """
    a_n, b_n = normalize(a), normalize(b)
    if not a_n or not b_n:
        return 0.0
    s1 = fuzz.token_set_ratio(a_n, b_n) / 100.0
    s2 = fuzz.WRatio(a_n, b_n) / 100.0
    return max(s1, s2)

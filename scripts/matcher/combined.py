"""Orquesta los tres métodos y devuelve un ``MatchResult`` único.

Reglas (en orden):
 1. Coincidencia exacta → similarity=1.0, método=``exact``, confidence=``high``.
 2. Fuzzy ≥ threshold → método=``fuzzy``, similarity=score; confidence según
    score (``high`` si ≥ 0.95, si no ``medium``).
 3. Fonético idéntico → similarity=0.70, método=``phonetic``, confidence=``medium``.
 4. Ninguno → no-match, similarity=max de los tres, método=``fuzzy``, confidence=``low``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scripts.matcher.exact import exact_score
from scripts.matcher.fuzzy import fuzzy_score
from scripts.matcher.phonetic import phonetic_score


Method = Literal["exact", "fuzzy", "phonetic"]
Confidence = Literal["high", "medium", "low"]


@dataclass
class MatchResult:
    is_match: bool
    similarity: float
    method: Method
    confidence: Confidence


@dataclass
class Thresholds:
    fuzzy: float = 0.80

    @classmethod
    def from_settings(cls, match_threshold: int, fuzzy_threshold: int) -> "Thresholds":
        return cls(fuzzy=fuzzy_threshold / 100.0)


def score_pair(
    watch_name: str,
    candidate: str,
    thresholds: Thresholds | None = None,
) -> MatchResult:
    """Compara ``watch_name`` contra ``candidate`` y devuelve el resultado."""
    th = thresholds or Thresholds()

    e = exact_score(watch_name, candidate)
    if e >= 1.0:
        return MatchResult(True, 1.0, "exact", "high")

    f = fuzzy_score(watch_name, candidate)
    if f >= th.fuzzy:
        confidence: Confidence = "high" if f >= 0.95 else "medium"
        return MatchResult(True, f, "fuzzy", confidence)

    p = phonetic_score(watch_name, candidate)
    if p >= 1.0:
        return MatchResult(True, 0.70, "phonetic", "medium")

    return MatchResult(False, max(e, f, p), "fuzzy", "low")


def find_matches(
    watch_names: list[str],
    candidates: list[str],
    thresholds: Thresholds | None = None,
) -> list[tuple[str, str, MatchResult]]:
    """Compara cada candidato contra cada watchlist y devuelve los matches.

    ``watch_names`` debe ser una lista de strings (los nombres de la
    watchlist del usuario). ``candidates`` los nombres extraídos del
    boletín. Devuelve tuplas ``(watch_name, candidate, result)`` solo
    para los pares donde ``result.is_match`` es True.
    """
    out: list[tuple[str, str, MatchResult]] = []
    for w in watch_names:
        for c in candidates:
            r = score_pair(w, c, thresholds)
            if r.is_match:
                out.append((w, c, r))
    return out

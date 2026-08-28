"""Orquesta los tres métodos y devuelve un ``MatchResult`` único.

Reglas (en orden):
  1. Si ``watch_class_nice`` y ``candidate_class_nice`` están ambos
     definidos y son distintos, **no es match** (mismatch de clase Niza).
     Esto reduce falsos positivos cuando una watchlist cubre una clase
     específica (p.ej. clase 25 = calzado) y el boletín publica clase 9.
  2. Coincidencia exacta → similarity=1.0, método=``exact``, confidence=``high``.
  3. Fuzzy ≥ threshold → método=``fuzzy``, similarity=score; confidence según
     score (``high`` si ≥ 0.95, si no ``medium``).
  4. Fonético idéntico → similarity=0.70, método=``phonetic``, confidence=``medium``.
  5. Ninguno → no-match, similarity=max de los tres, método=``fuzzy``, confidence=``low``.

Umbrales ajustables por usuario: ``Thresholds`` admite ``fuzzy`` y
``phonetic_floor``. Si el usuario quiere ser más estricto, sube ``fuzzy``
(p.ej. 0.90). Si quiere permitir fonético más débil, baja ``phonetic_floor``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

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
    class_nice_check: Optional[str] = None  # "ok" | "mismatch" | "unknown"


@dataclass
class Thresholds:
    fuzzy: float = 0.80
    phonetic_floor: float = 1.0  # fonético idéntico=1.0 por defecto

    @classmethod
    def from_settings(cls, match_threshold: int, fuzzy_threshold: int) -> "Thresholds":
        return cls(fuzzy=fuzzy_threshold / 100.0)

    @classmethod
    def from_user(
        cls,
        *,
        fuzzy_pct: Optional[int] = None,
        phonetic_floor: Optional[float] = None,
        fallback: "Thresholds | None" = None,
    ) -> "Thresholds":
        """Umbrales ajustables por usuario. ``None`` ⇒ usa el fallback (defaults)."""
        base = fallback or cls()
        return cls(
            fuzzy=(fuzzy_pct / 100.0) if fuzzy_pct is not None else base.fuzzy,
            phonetic_floor=phonetic_floor if phonetic_floor is not None else base.phonetic_floor,
        )


def score_pair(
    watch_name: str,
    candidate: str,
    thresholds: Thresholds | None = None,
    *,
    watch_class_nice: Optional[int] = None,
    candidate_class_nice: Optional[int] = None,
) -> MatchResult:
    """Compara ``watch_name`` contra ``candidate`` y devuelve el resultado.

    Si ambos ``class_nice`` están definidos y son distintos, devuelve un
    no-match con ``class_nice_check='mismatch'`` (ver regla 1).
    """
    th = thresholds or Thresholds()

    # G.1 — cruce de clase Niza: si ambos lados tienen clase y no coinciden,
    # NO es match (reduce falsos positivos).
    if (
        watch_class_nice is not None
        and candidate_class_nice is not None
        and watch_class_nice != candidate_class_nice
    ):
        return MatchResult(
            is_match=False,
            similarity=0.0,
            method="fuzzy",
            confidence="low",
            class_nice_check="mismatch",
        )

    class_check = "ok" if watch_class_nice is not None or candidate_class_nice is not None else "unknown"

    e = exact_score(watch_name, candidate)
    if e >= 1.0:
        return MatchResult(True, 1.0, "exact", "high", class_check)

    f = fuzzy_score(watch_name, candidate)
    if f >= th.fuzzy:
        confidence: Confidence = "high" if f >= 0.95 else "medium"
        return MatchResult(True, f, "fuzzy", confidence, class_check)

    p = phonetic_score(watch_name, candidate)
    if p >= th.phonetic_floor:
        return MatchResult(True, 0.70, "phonetic", "medium", class_check)

    return MatchResult(False, max(e, f, p), "fuzzy", "low", class_check)


def find_matches(
    watch_names: list[str],
    candidates: list[str],
    thresholds: Thresholds | None = None,
    *,
    watch_class_nices: Optional[list[Optional[int]]] = None,
    candidate_class_nices: Optional[list[Optional[int]]] = None,
) -> list[tuple[str, str, MatchResult]]:
    """Compara cada candidato contra cada watchlist y devuelve los matches.

    ``watch_class_nices`` y ``candidate_class_nices`` son listas paralelas
    a ``watch_names`` y ``candidates`` con sus clases Niza (o ``None``).

    Devuelve tuplas ``(watch_name, candidate, result)`` solo para los pares
    donde ``result.is_match`` es True.
    """
    out: list[tuple[str, str, MatchResult]] = []
    w_classes = watch_class_nices or [None] * len(watch_names)
    c_classes = candidate_class_nices or [None] * len(candidates)
    for w, w_class in zip(watch_names, w_classes):
        for c, c_class in zip(candidates, c_classes):
            r = score_pair(
                w, c, thresholds,
                watch_class_nice=w_class,
                candidate_class_nice=c_class,
            )
            if r.is_match:
                out.append((w, c, r))
    return out

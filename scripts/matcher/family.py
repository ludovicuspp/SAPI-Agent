"""Contención de marca (familias) para matching.

Una marca puede aparecer en el boletín con la misma familia pero con
sufijos descriptivos: ``DRAGON`` en watchlist vs ``DRAGON WINCH`` en el
boletín. ``family_score`` captura esa relación de contención: la marca
vigilada aporta tokens núcleo y se verifica que estén contenidos en el
candidato.

Se usa como regla adicional cuando la clase Niza está lejana
(detección de conflicto) o cuando la watchlist tiene ``match_family=1``.
"""
from __future__ import annotations

import re

# Términos que no aportan identidad de marca (razones sociales, fórmulas
# legales, genéricos comerciales).
_NON_BRAND = {
    "ca", "cia", "co", "compania", "compañia", "corp", "corporacion",
    "corporación", "de", "del", "e", "empresa", "export", "import", "inc",
    "industria", "ltd", "llc", "los", "las", "srl", "sa", "ss", "y",
    "agencia", "representaciones", "servicios", "taller", "comercial",
}


def core_tokens(value: str | None) -> list[str]:
    """Tokens significativos de un nombre de marca (sin razones sociales)."""
    if not value:
        return []
    tokens = [t.lower() for t in re.findall(r"[a-z0-9]+", value.lower())]
    return [t for t in tokens if t not in _NON_BRAND]


def family_score(watch_name: str, candidate: str) -> float:
    """Score de contención de familia (0..1), mayor = contención fuerte.

    Devuelve la fracción de tokens núcleo de ``watch_name`` presentes en
    ``candidate``. 1.0 = el candidato contiene toda la marca vigilada.
    0.0 si el watchlist no aporta tokens núcleo.
    """
    wa = core_tokens(watch_name)
    ca = core_tokens(candidate)
    if not wa or not ca:
        return 0.0
    common = sum(1 for t in wa if t in ca)
    return common / len(wa)


def family_overlap(name_a: str, name_b: str) -> float:
    """Superposición de tokens (simétrica) entre dos marcas (0..1)."""
    a = set(core_tokens(name_a))
    b = set(core_tokens(name_b))
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
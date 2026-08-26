"""Pattern C: Inscripción + SOLICITADA POR sin marca denominativa.

Cubre entradas con ``Insc.`` + ``SOLICITADA POR:`` + ``DESCRIPCION DE
ETIQUETA:`` y ningún nombre de marca textual. La marca es figurativa;
queda con ``matcheable=False`` para que visión (Hermes) la refine.

Pattern A y B ya cubren la mayoría; Pattern C es el fallback para
entradas que solo A puede extraer pero sin marca denominativa.
En la práctica, Pattern C rara vez produce entries nuevas: cuando A no
encuentra marca denominativa, devuelve ``matcheable=False`` y ``es_figura=True``.
Pattern C existe por simetría y para futuras heurísticas de captura
de elementos gráficos (logos, etiquetas).
"""
from __future__ import annotations

from typing import Iterator

from scripts.parsers.patterns.base import (
    DESCRIPCION_ETIQUETA_RE,
    INSC_RE,
)


def extract(text: str) -> Iterator[dict]:
    """Itera sobre entradas con ``Insc.`` + ``SOLICITADA POR:`` pero
    sin marca denominativa detectada por Pattern A o B.

    Devuelve entries con ``matcheable=False`` y ``es_figura=True``
    para que queden en el lote de visión (Hermes).
    """
    blocks = INSC_RE.split(text)
    n = len(blocks)
    if n == 1:
        return
    for i in range(1, n, 3):
        if i + 2 >= n:
            continue
        expediente = blocks[i]
        content = blocks[i + 2]
        next_insc = INSC_RE.search(content)
        if next_insc:
            content = content[:next_insc.start()]

        if "SOLICITADA POR" not in content.upper():
            continue
        if DESCRIPCION_ETIQUETA_RE.search(content) is None:
            continue
        from scripts.parsers.patterns.base import NOMBRE_MARCA_RE
        if NOMBRE_MARCA_RE.search(content):
            continue

        yield {
            "expediente": expediente.strip(),
            "marca": None,
            "clase_niza": None,
            "clase_especial": None,
            "titular": None,
            "pais": None,
            "fecha_inscripcion": None,
            "es_figura": True,
            "matcheable": False,
            "excerpt": f"Insc. {expediente}\n" + content[:500].strip(),
        }

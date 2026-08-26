"""Pattern B: Inscripción + ``NOMBRE DE LA MARCA:`` explícito.

Variantes de orden observadas:
1. Insc. + NOMBRE DE LA MARCA: + SOLICITADA POR: + ... (BPI 651, 655)
2. Insc. + SOLICITADA POR: + ... + EN CLASE + NOMBRE DE LA MARCA: (raro)
3. Insc. + SOLICITADA POR: + Domicilio + País + (sin NOMBRE) → cae al Pattern A

Este pattern busca ``NOMBRE DE LA MARCA:`` en cualquier posición entre
``Insc.`` y la siguiente ``Insc.`` (o fin de bloque).
"""
from __future__ import annotations

from typing import Iterator

from scripts.parsers.patterns.base import (
    CLASE_RE,
    INSC_RE,
    NOMBRE_MARCA_RE,
    PAIS_RE,
    SOLICITADA_RE,
    clean_marca,
    clean_titular,
    normalize_fecha,
    normalize_pais,
    parse_clase,
)
from scripts.parsers.patterns.pattern_a import _entry_from_block


def extract(text: str) -> Iterator[dict]:
    """Itera sobre cada ``Insc.`` que tenga ``NOMBRE DE LA MARCA:``
    en su bloque.
    """
    blocks = INSC_RE.split(text)
    n = len(blocks)
    if n == 1:
        return
    for i in range(1, n, 3):
        if i + 2 >= n:
            continue
        expediente = blocks[i]
        fecha_raw = blocks[i + 1]
        content = blocks[i + 2]

        next_insc = INSC_RE.search(content)
        if next_insc:
            content = content[:next_insc.start()]

        nombre_m = NOMBRE_MARCA_RE.search(content)
        if not nombre_m:
            continue  # este bloque no aplica Pattern B

        base = _entry_from_block(expediente, fecha_raw, content)
        marca = clean_marca(nombre_m.group("marca"))
        base["marca"] = marca
        base["matcheable"] = marca is not None
        base["es_figura"] = False
        yield base

"""Pattern A: Inscripción + Solicitada + Marca-línea(s) + Clase.

Caso más común en BPI 651-655. La marca aparece como una o dos líneas
en MAYÚSCULAS sostenidas entre ``País:`` (o ``SOLICITADA POR:``) y
``EN CLASE:``.

Ejemplo (BPI 651 p.8):
    Insc. 2015-015976 del 30 DE OCTUBRE DE 2015
    SOLICITADA POR: RAUL ENRIQUE ARTIGAS Domicilio: BARQUISIMETO, EDO. LARA País:
    VENEZUELA
    TRIPLE MILLONARIO
    EN CLASE: 35
    PARA DISTINGUIR: LA GESTIÓN DE NEGOCIOS...

Ejemplo multi-línea (BPI 654 p.1251):
    Insc. 2026-001274 del 12 DE FEBRERO DE 2026
    SOLICITADA POR:
     UCAMAY CORP, C.A. Domicilio: LA GUAIRA, LA GUAIRA País: VENEZUELA
    UCAMAY CALM RESTORE
    EN CLASE:    3
"""
from __future__ import annotations

from typing import Iterator

from scripts.parsers.patterns.base import (
    CLASE_RE,
    DESCRIPCION_ETIQUETA_RE,
    INSC_RE,
    PAIS_RE,
    SOLICITADA_RE,
    clean_marca,
    clean_titular,
    extract_brand_lines,
    normalize_fecha,
    normalize_pais,
    parse_clase,
)


def _entry_from_block(expediente: str, fecha_raw: str, content: str) -> dict:
    """Construye el dict de campos a partir del bloque de texto de una
    entrada. Usado por Pattern A y Pattern C."""
    titular_m = SOLICITADA_RE.search(content)
    clase_m = CLASE_RE.search(content)
    pais_m = PAIS_RE.search(content)

    titular = clean_titular(titular_m.group("titular")) if titular_m else None
    pais_raw = pais_m.group("pais") if pais_m else None
    pais = normalize_pais(pais_raw)
    clase_niza, clase_especial = parse_clase(clase_m.group("clase") if clase_m else None)

    # Marca: líneas en MAYÚSCULAS entre País (o SOLICITADA POR) y EN CLASE.
    marca_lines = []
    if pais_m:
        marca_lines = extract_brand_lines(content, pais_m.end(), clase_m.start() if clase_m else len(content))
    elif titular_m and clase_m:
        marca_lines = extract_brand_lines(content, titular_m.end(), clase_m.start())
    marca_raw = " ".join(marca_lines) if marca_lines else None
    marca = clean_marca(marca_raw) if marca_raw else None

    es_figura = (
        marca is None
        and DESCRIPCION_ETIQUETA_RE.search(content) is not None
    )

    # El excerpt empieza con "Insc." para que el processor pueda localizarlo
    # en el texto del boletín por posición.
    excerpt = f"Insc. {expediente} del {fecha_raw}\n" + content[:500].strip()

    return {
        "expediente": expediente.strip(),
        "marca": marca,
        "clase_niza": clase_niza,
        "clase_especial": clase_especial,
        "titular": titular,
        "pais": pais,
        "fecha_inscripcion": normalize_fecha(fecha_raw),
        "es_figura": es_figura,
        "matcheable": marca is not None,
        "excerpt": excerpt,
    }


def extract(text: str) -> Iterator[dict]:
    """Itera sobre cada ``Insc.`` y devuelve los campos parseados.

    Cada ``yield`` devuelve un dict con las claves:
        expediente, marca, clase_niza, clase_especial, titular, pais,
        fecha_inscripcion, es_figura, matcheable, excerpt.
    """
    blocks = INSC_RE.split(text)
    # blocks = [pre, exp1, fecha1, content1, exp2, fecha2, content2, ...]
    # Si hay un solo bloque Insc. y el texto no termina con él, ``content`` es el resto.
    n = len(blocks)
    if n == 1:
        # Sin inscripciones.
        return
    # Procesar todas las tripletas (expediente, fecha, content).
    # Si n=4, hay una sola inscripción con su contenido: [pre, exp, fecha, content].
    # Si n=7, hay dos: [pre, e1, f1, c1, e2, f2, c2].
    # Si n=4 pero blocks[3] está vacío (Insc. al final sin contenido), lo saltamos.
    for i in range(1, n, 3):
        if i + 2 >= n:
            # El último bloque está incompleto (no hay contenido).
            if i + 1 < n and not blocks[i + 1]:
                continue
            if i + 2 >= n and (i + 1 >= n or not blocks[i + 1]):
                continue
        expediente = blocks[i]
        fecha_raw = blocks[i + 1] if i + 1 < n else ""
        content = blocks[i + 2] if i + 2 < n else ""

        # Cortar el bloque en la siguiente Inscripción.
        next_insc = INSC_RE.search(content)
        if next_insc:
            content = content[:next_insc.start()]

        yield _entry_from_block(expediente, fecha_raw, content)

"""Pattern D: resoluciones de la sección DISPOSICIONES ADMINISTRATIVAS.

La sección no contiene inscripciones ("Insc. ...") sino RESOLUCIONES
administrativas (recursos de reconsideración, caducidad, etc.) que citan
solicitudes en tablas (N° / SOLICITUD / MARCA / CLASE / SOLICITANTE) y
terminan con una fórmula de decisión ("RESUELVE ...").

Observaciones sobre boletines reales (BPI 654, tomos XVII-XVIII):

- El encabezado "Disposiciones Administrativas" SOLO aparece en los
  índices, con puntos de relleno (". . . . Pág. NN"); la sección de
  contenido arranca directamente con el preámbulo ministerial seguido
  de "RESOLUCIÓN Nº". Por eso el ancla de bloque es la línea
  ``RESOLUCIÓN`` y el filtro es el preámbulo, no el título de sección.
- El número de la resolución suele salir con glyphs rotos; no se usa.
- La decisión vive al final del bloque ("RESUELVE ... decide: 1. ...").
  Ahí se afirma la distinción entre DEVUELTA de forma y de fondo, se
  REVOCAN/CONFIRMAN resoluciones previas, se CONCEDEN signos y se
  declara la CADUCIDAD. También fija el lapso de pago de la concesión
  ("treinta (30) días hábiles"), insumo del módulo de lapsos.

Cada resolución genera una entrada por solicitud citada, con el texto
de la decisión en ``disposicion`` y su tipo normalizado en
``tipo_disposicion`` (conjunto cerrado ``DisposicionTipoLiteral``).
"""
from __future__ import annotations

import re
from typing import Iterator, Optional

from scripts.parsers.patterns.base import is_upperish

# Ancla de bloque: línea que arranca con RESOLUCIÓN.
_RESOLUCION_RE = re.compile(r"^RESOLUCI[ÓO]N\b.*$", re.MULTILINE)

# Preámbulo de una resolución real (primeros caracteres del bloque).
_PREAMBULO_RE = re.compile(
    r"(VISTOS|VISTAS|MINISTERIO\s+DEL\s+PODER|REP[ÚU]BLICA\s+BOLIVARIANA|CARACAS\s*,)",
    re.IGNORECASE,
)

# Marcadores de sección de devolución dentro del bloque de resolución
# (BPI 654: "RESOLUCIÓN N°\nDEVUELTAS DE FORMA\nVISTAS LAS SOLICITUDES...").
_DEV_FORMA_RE = re.compile(r"DEVUELTAS?\s+DE\s+FORMA", re.IGNORECASE)
_DEV_FONDO_RE = re.compile(r"DEVUELTAS?\s+DE\s+FONDO", re.IGNORECASE)

# "NC" en la tabla de devueltas = sin clase Niza.
_SIN_CLASE_RE = re.compile(r"^\s*N\s*[/\.]?\s*C\s*$", re.IGNORECASE)

# Referencias que NO son solicitudes (no llevan formato AAAA-NNNNNN).
_EXPEDIENTE_RE = re.compile(r"\b(\d{4}-\d{4,6})\b")

# Palabras de cabecera de la tabla que no son datos.
_TABLA_WORDS = {"SOLICITUD", "MARCA", "CLASE", "SOLICITANTE", "N°", "Nº", "N"}
_LINEA_CLASE_RE = re.compile(r"^\s*(\d{1,2})\s*INT\b\.?\s*$")
_LINEA_NUMERO_RE = re.compile(r"^\s*(\d{1,2})\s*\.?\s*$")
_LINEA_FILA_RE = re.compile(r"^\s*\d{1,3}\.\s*$")
_LINEA_MARCA_RE = re.compile(r"^[A-ZÁÉÍÓÚÑÜ0-9(][A-ZÁÉÍÓÚÑÜ0-9 .,&'()\-/]{1,79}$")

# Límites de texto por resolución (el boletín es un PDF grande; los
# excerpts no deben crecer sin tope).
_DECISION_MAX = 900
_EXCERPT_MAX = 500


def _limpia(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _es_marca(linea: str) -> bool:
    """Una línea de tabla parece un nombre de marca (mayúsculas)."""
    l = linea.strip()
    if not l or l.upper() in _TABLA_WORDS:
        return False
    if _LINEA_FILA_RE.match(linea) or _LINEA_CLASE_RE.match(linea):
        return False
    if l.isdigit():
        return False
    return bool(_LINEA_MARCA_RE.match(l)) and is_upperish(l)


def _decision_del_bloque(bloque: str) -> str:
    """Texto de la decisión: desde el último 'RESUELVE' (o el inicio)."""
    idx = bloque.rfind("RESUELVE")
    if idx < 0:
        return _limpia(bloque[:_EXCERPT_MAX])
    return _limpia(bloque[idx : idx + _DECISION_MAX])


_TIPOS: list[tuple[str, str]] = [
    # Orden de prioridad: el tipo es el efecto neto sobre la MARCA (no
    # sobre el recurso). P.ej. "INADMISIBLE el escrito + CONFIRMA la
    # negación" → NEGACION, porque la negación queda firme. Se comparan
    # contra el texto de la decisión YA en mayúsculas.
    (r"CADUCIDAD", "CADUCA"),
    (r"\bCONCED\w*", "CONCESION"),
    (r"\bNIEG[OA]\b|\bNEGAR\b|\bNEGADO\b|\bCONFIRMA\b", "NEGACION"),
    (r"INADMISIBLE", "INADMISIBLE"),
    (r"\bREVOC\w*", "REVOCA"),
]


def _tipo_de(bloque: str, decision: str) -> Optional[str]:
    """Tipo de disposición: primero los marcadores de sección de
    devolución del bloque (forma vs fondo), luego la decisión."""
    if _DEV_FORMA_RE.search(bloque):
        return "DEVOLUCION_FORMA"
    if _DEV_FONDO_RE.search(bloque):
        return "DEVOLUCION_FONDO"
    d = decision.upper()
    for pat, tipo in _TIPOS:
        if re.search(pat, d):
            return tipo
    return None


def _campos_de_fila(
    lineas: list[str], i: int
) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """Extrae (marca, clase_niza, titular) de la fila que arranca en ``i``
    (la línea del expediente). Devuelve (None, None, None) si no hay datos.

    Soporta dos formatos reales del boletín:

    - Reconsideración: expediente / MARCA (1-2 líneas) / "NN INT" /
      SOLICITANTE (1-2 líneas).
    - Devueltas de forma/fondo: expediente / clase ("36" o "NC") /
      MARCA / titular con prosa "Domicilio:".
    """
    marca: Optional[str] = None
    clase: Optional[int] = None
    titular: Optional[str] = None
    j = i + 1
    partes: list[str] = []
    # Formato devueltas: la clase numérica va ANTES de la marca y la
    # marca cabe en una sola línea (el titular sigue en mayúsculas).
    marca_una_linea = False
    while j < len(lineas) and len(partes) < 3:
        l = lineas[j]
        if _LINEA_FILA_RE.match(l):
            break
        m_clase = _LINEA_CLASE_RE.match(l)
        if m_clase:
            clase = int(m_clase.group(1))
            j += 1
            break
        if _SIN_CLASE_RE.match(l):
            j += 1
            marca_una_linea = True
            continue
        if _LINEA_NUMERO_RE.match(l) and not l.strip().endswith("."):
            # Clase sin sufijo ("36"): antes de la marca (formato
            # devueltas) continúa la búsqueda; después de la marca
            # (formato reconsideración sin INT) la cierra.
            clase = int(l.strip())
            j += 1
            if partes:
                break
            marca_una_linea = True
            continue
        if _es_marca(l):
            partes.append(_limpia(l))
            j += 1
            if marca_una_linea:
                break
            continue
        break
    if partes:
        marca = " ".join(partes)
    # Titular: líneas siguientes a la clase, hasta la próxima fila.
    # Solo líneas en mayúsculas y sin prosa de domicilio: el titular de
    # las tablas de devolución va mezclado con "Domicilio: ...".
    partes_t: list[str] = []
    while j < len(lineas) and len(partes_t) < 3:
        l = lineas[j]
        if _LINEA_FILA_RE.match(l):
            break
        if _LINEA_CLASE_RE.match(l) or l.strip().isdigit():
            break
        if "domicilio" in l.lower() or "país" in l.lower():
            break
        if len(l.strip()) >= 3 and is_upperish(l):
            partes_t.append(_limpia(l))
            j += 1
            continue
        break
    if partes_t:
        titular = " ".join(partes_t)
    return marca, clase, titular


def extract(text: str) -> Iterator[dict]:
    """Itera las solicitudes citadas en las resoluciones del boletín.

    Cada ``yield`` devuelve un dict con las claves: ``expediente``,
    ``marca``, ``clase_niza``, ``titular``, ``disposicion``,
    ``tipo_disposicion``, ``matcheable``, ``excerpt``. Sin expedientes
    citados no se emite nada (el excerpt de la resolución no entra al
    inventario de marcas).
    """
    bloques = _RESOLUCION_RE.split(text)
    # blocks = [pre, bloque1, bloque2, ...]; cada bloque empieza justo
    # después de la línea RESOLUCIÓN.
    n = len(bloques)
    if n < 2:
        return
    for bloque in bloques[1:]:
        # Filtro de preámbulo: descarta nombres de marca que empiezan
        # con "RESOLUCIÓN" (dentro de entradas de otras secciones).
        if not _PREAMBULO_RE.search(bloque[:600]):
            continue
        decision = _decision_del_bloque(bloque)
        tipo = _tipo_de(bloque, decision)
        lineas = bloque.splitlines()
        # Posición de cada línea para armar el excerpt localizable.
        offset = 0
        emitidas: set[str] = set()
        for i, linea in enumerate(lineas):
            m = _EXPEDIENTE_RE.search(linea)
            if not m:
                continue
            expediente = m.group(1)
            if expediente in emitidas:
                continue
            emitidas.add(expediente)
            marca, clase, titular = _campos_de_fila(lineas, i)
            # Excerpt crudo (sin colapsar espacios): _enrich lo localiza
            # literalmente en el texto para asignar la página.
            excerpt = "\n".join(lineas[i : i + 8]).strip()
            yield {
                "expediente": expediente,
                "marca": marca,
                "clase_niza": clase,
                "titular": titular,
                "pais": None,
                "disposicion": decision,
                "tipo_disposicion": tipo,
                "matcheable": marca is not None,
                "excerpt": excerpt,
            }

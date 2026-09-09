"""Seguimiento del expediente de las marcas del portfolio (Fase 3).

Deriva, a partir de los boletines extraídos, la línea de tiempo del
trámite de cada marca propia: cada aparición del expediente (o el
nombre + clase Niza si el usuario no registró número) es un hito con
su estatus y disposición. El estado actual del trámite es el último
hito en el tiempo.
"""
from __future__ import annotations

from typing import Any, Optional

from scripts import db
from scripts.matcher.exact import normalize as norm


# ── Estados del trámite ─────────────────────────────────────────


def estado_from_hit(estatus: Optional[str], tipo_disposicion: Optional[str]) -> str:
    """Estado del trámite que deriva de una aparición en el boletín."""
    if tipo_disposicion:
        por_tipo = {
            "CONCESION": "CONCEDIDA",
            "NEGACION": "NEGADA",
            "DEVOLUCION_FORMA": "DEVUELTA_FORMA",
            "DEVOLUCION_FONDO": "DEVUELTA_FONDO",
            "CADUCA": "CADUCA",
            "REVOCA": "REVOCADA",
            "INADMISIBLE": "INADMISIBLE",
        }
        if tipo_disposicion in por_tipo:
            return por_tipo[tipo_disposicion]
    por_estatus = {
        "PUBLICADA": "PUBLICADA",
        "CONCEDIDA": "CONCEDIDA",
        "NEGADA": "NEGADA",
        "CADUCA": "CADUCA",
        "DESISTIDA": "DESISTIDA",
        "RENOVADA": "RENOVADA",
        "DEVUELTA": "DEVUELTA_FORMA",
    }
    if estatus in por_estatus:
        return por_estatus[estatus]
    return "SOLICITADA"


def _marca_variants(name: str) -> list[str]:
    """Variantes NOCASE del nombre para la query de candidatos."""
    def collapse(s: str) -> str:
        return " ".join(s.split())

    base = collapse(name)
    variants = {base, base.upper(), base.lower()}
    if norm(name):
        variants.add(collapse(norm(name)))
    variants.discard("")
    return sorted(variants, key=len, reverse=True)


def _hitos_for_portfolio(
    conn: Any, portfolio: db.PortfolioRow, user_id: int | None
) -> tuple[list[dict], bool]:
    """Hitos candidatos del expediente."""

    def por_expediente() -> tuple[list[dict], bool]:
        if portfolio.expediente and norm(portfolio.expediente):
            rows = db.expediente_hitos(
                conn, user_id=user_id, expediente=portfolio.expediente
            )
            if rows:
                return rows, True
        return [], False

    filas, matched = por_expediente()
    if matched:
        return filas, True
    # Fallback: por nombre + clase.
    return (
        db.expediente_hitos(
            conn,
            user_id=user_id,
            marca_variants=_marca_variants(portfolio.name),
            class_nice=portfolio.class_nice,
        ),
        False,
    )


def derivar_expediente(
    conn, portfolio: db.PortfolioRow, *, user_id: int | None
) -> dict:
    """Línea de tiempo del trámite de una marca del portfolio.

    Combina dos fuentes:
    - ``boletines``: apariciones directas del expediente (o nombre+clase)
      en los boletines extraídos visible para el usuario.
    - ``detecciones``: las que el matcher ligó a este portfolio
      (importa ver los conflictos que le aparecen a la marca).

    Devuelve: ``hitos`` (más reciente primero), ``estado`` derivado de
    las apariciones propias del trámite (entries o `match_kind="own_status"`),
    ``expedientes`` y ``marcadas`` (números/nombres distintos observados).
    """
    raw, por_expediente = _hitos_for_portfolio(conn, portfolio, user_id)

    # Apariciones que el matcher ligó a este portfolio.
    if user_id is not None:
        det_rows = db.detections_for_portfolio(conn, portfolio.id, user_id)
    else:
        det_rows = db.detections_for_portfolio(
            conn, portfolio.id, portfolio.user_id
        )

    # Filtro de precisión: solo apariciones cuyo nombre coincide
    # normalizado con la marca del portfolio (omitido si se matcheó
    # por número de expediente exacto: es la caja propia del trámite).
    norm_name = norm(portfolio.name)
    por_clave: dict[tuple, dict] = {}

    def _peso_hito(h: dict) -> int:
        # Prioriza el hito que aporta estado (disposición o trámite propio).
        return (1 if h.get("tipo_disposicion") else 0) + (
            1 if h.get("es_propio") else 0
        )

    def _meter(h: dict) -> None:
        clave = (h["boletin_id"], h["expediente"], h["page"])
        prev = por_clave.get(clave)
        if prev is None or _peso_hito(h) > _peso_hito(prev):
            por_clave[clave] = h

    for h in raw:
        if not por_expediente:
            marca_norm = norm(h.get("marca") or "")
            if not (marca_norm and marca_norm == norm_name):
                continue
        h["es_propio"] = True
        h["origen"] = "boletin"
        h["detection_id"] = None
        _meter(h)

    # Apariciones que el matcher ligó a este portfolio.
    for d in det_rows:
        d["es_propio"] = d.get("match_kind") == "own_status"
        d["entry_id"] = None
        _meter(d)

    hitos = list(por_clave.values())

    hitos.sort(
        key=lambda h: (
            h.get("fecha_publicacion") is None,
            h.get("fecha_publicacion") or "",
            h["boletin_id"],
            h["page"] or 0,
        ),
        reverse=True,
    )
    expedientes = sorted({h["expediente"] for h in hitos if h["expediente"]})
    marcadas = sorted({h["marca"] for h in hitos if h["marca"]})

    # Estado: solo artefactos propios del trámite.
    propios = [h for h in hitos if h.get("es_propio")]
    estado = "SIN_MOVIMIENTO"
    ultimo = propios[0] if propios else None
    if ultimo:
        estado = estado_from_hit(ultimo.get("estatus"), ultimo.get("tipo_disposicion"))

    return {
        "hitos": hitos,
        "estado": estado,
        "expedientes": expedientes,
        "marcadas": marcadas,
        "user_id": user_id,
        "portfolio_id": portfolio.id,
    }
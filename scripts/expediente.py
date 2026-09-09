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
) -> list[dict]:
    """Hitos del expediente. ``user_id=None`` (admin) ve todos."""
    if portfolio.expediente and norm(portfolio.expediente):
        hitos = db.expediente_hitos(
            conn, user_id=user_id, expediente=portfolio.expediente
        )
        if hitos:
            return hitos
    # Fallback: por nombre + clase.
    return db.expediente_hitos(
        conn,
        user_id=user_id,
        marca_variants=_marca_variants(portfolio.name),
        class_nice=portfolio.class_nice,
    )


def derivar_expediente(
    conn, portfolio: db.PortfolioRow, *, user_id: int | None
) -> dict:
    """Línea de tiempo del trámite de una marca del portfolio.

    Devuelve: ``hitos`` (ordenados de más reciente a más antiguo),
    ``estado`` derivado del último hito (o ``SIN_MOVIMIENTO``),
    ``expedientes`` (números distintos observados) y ``marcadas``
    (nombres distintos observados).
    """
    raw = _hitos_for_portfolio(conn, portfolio, user_id)

    # Filtro de precisión: solo apariciones cuyo nombre coincide
    # normalizado con la marca del portfolio.
    norm_name = norm(portfolio.name)
    hitos: list[dict] = []
    seen: set[tuple] = set()
    for h in raw:
        marca_norm = norm(h.get("marca") or "")
        if not (marca_norm and marca_norm == norm_name):
            continue
        clave = (h["boletin_id"], h["expediente"], h["page"])
        if clave in seen:
            continue
        seen.add(clave)
        hitos.append(h)

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

    estado = "SIN_MOVIMIENTO"
    ultimo = hitos[0] if hitos else None
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
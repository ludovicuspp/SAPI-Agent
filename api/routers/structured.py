"""POST /api/boletines/{boletin_id}/structured — Hermes entrega entries procesadas."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from scripts import db
from scripts.config import get_settings
from scripts.matcher import combined
from scripts.schemas import StructuredBoletinIn, StructuredOut
from api.deps import get_db, require_hermes

router = APIRouter()

_MAX_ENTRIES_PER_REQUEST = 100
_MAX_MATCHES_PER_ENTRY = 5


@router.post("/{boletin_id}/structured", response_model=StructuredOut)
async def submit_structured(
    boletin_id: int,
    payload: StructuredBoletinIn,
    conn: sqlite3.Connection = Depends(get_db),
    _hermes: None = Depends(require_hermes),
):
    if payload.boletin_id != boletin_id:
        raise HTTPException(status_code=400, detail="boletin_id mismatch")
    if len(payload.entries) > _MAX_ENTRIES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"Max {_MAX_ENTRIES_PER_REQUEST} entries por request")

    boletin = db.boletines_get(conn, boletin_id)
    if boletin is None:
        raise HTTPException(status_code=404, detail="Boletín no encontrado")

    if boletin.hermes_processed_at:
        return StructuredOut(boletin_id=boletin_id, status="already_processed", entries_added=0)

    cfg = get_settings()
    thresholds = combined.Thresholds.from_settings(cfg.match_threshold, cfg.fuzzy_threshold)

    entries_added = 0

    for entry in payload.entries:
        # Buscar matches contra TODAS las watchlists activas (multi-tenant).
        # Cap top-N por similitud para evitar explosión (entradas alucinadas
        # con muchas watchlists no deben generar miles de detections).
        watch_candidates: list[tuple] = []
        for user in db.users_list(conn):
            user_watch = db.watchlist_list_for_user(conn, user.id, only_active=True)
            for w in user_watch:
                mr = combined.score_pair(w.name, entry.marca, thresholds)
                if mr.is_match:
                    watch_candidates.append((mr.similarity, user.id, w, mr))

        watch_candidates.sort(key=lambda t: t[0], reverse=True)
        for _sim, user_id, w, mr in watch_candidates[:_MAX_MATCHES_PER_ENTRY]:
            db.detections_add(
                conn,
                boletin_id=boletin_id,
                user_id=user_id,
                watchlist_id=w.id,
                mark_name=entry.marca,
                similarity=mr.similarity,
                match_kind="similar",
                source=entry.fuente,
                confidence=entry.confianza,
                expediente=entry.expediente,
                titular=entry.titular,
                class_nice=entry.clase_niza,
                page=entry.pagina,
                raw_excerpt=entry.excerpt,
                pais=entry.pais,
                fecha_inscripcion=(
                    entry.fecha_inscripcion.isoformat()
                    if hasattr(entry.fecha_inscripcion, "isoformat")
                    else entry.fecha_inscripcion
                ),
                fuente_parsing="hermes",
            )
            entries_added += 1

        # Match contra portafolios propios por expediente.
        for user in db.users_list(conn):
            user_portfolio = db.portfolio_list_for_user(conn, user.id)
            for p in user_portfolio:
                if p.expediente and p.expediente.strip() == entry.expediente.strip():
                    db.detections_add(
                        conn,
                        boletin_id=boletin_id,
                        user_id=user.id,
                        portfolio_id=p.id,
                        mark_name=entry.marca,
                        similarity=1.0,
                        match_kind="own_status",
                        source=entry.fuente,
                        confidence="high",
                        expediente=entry.expediente,
                        titular=entry.titular,
                        class_nice=entry.clase_niza,
                        page=entry.pagina,
                        raw_excerpt=entry.excerpt,
                        pais=entry.pais,
                        fecha_inscripcion=(
                            entry.fecha_inscripcion.isoformat()
                            if hasattr(entry.fecha_inscripcion, "isoformat")
                            else entry.fecha_inscripcion
                        ),
                        fuente_parsing="hermes",
                    )
                    if entry.estatus:
                        db.portfolio_update_status(conn, p.id, entry.estatus, user.id)
                    entries_added += 1

    conn.execute(
        "UPDATE boletines SET hermes_processed_at = datetime('now') WHERE id = ?",
        (boletin_id,),
    )
    conn.commit()
    return StructuredOut(boletin_id=boletin_id, status="processed", entries_added=entries_added)

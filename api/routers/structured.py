"""POST /api/boletines/{boletin_id}/structured — Hermes entrega entries procesadas."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from scripts import db
from scripts.config import get_settings
from scripts.matcher import combined
from scripts.orchestration.portfolio_sync import (
    match_portfolio_by_identity,
    match_portfolio_conflicts,
)
from scripts.orchestration.matching_service import (
    watch_entry_matches,
    watch_titular_matches,
)
from scripts.schemas import (
    HermesDoneIn,
    HermesDoneOut,
    HermesProgressIn,
    HermesProgressOut,
    StructuredBoletinIn,
    StructuredOut,
)
from api.deps import get_db, require_hermes

router = APIRouter()

_MAX_ENTRIES_PER_REQUEST = 100
_MAX_MATCHES_PER_ENTRY = 5


def _hermes_to_entry_like(entry):
    """Adapta ``StructuredEntryIn`` al duck-type esperado por
    ``match_portfolio_by_identity`` y ``match_portfolio_conflicts``
    (usan ``getattr`` con defaults)."""
    from types import SimpleNamespace

    return SimpleNamespace(
        marca=entry.marca,
        expediente=entry.expediente,
        clase_niza=entry.clase_niza,
        clase_especial=None,
        titular=entry.titular,
        pais=entry.pais,
        fecha_inscripcion=entry.fecha_inscripcion,
        page=getattr(entry, "pagina", None),
        excerpt=getattr(entry, "excerpt", None),
        es_figura=False,
        es_lema=False,
        productos_servicios=getattr(entry, "productos_servicios", None),
    )


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
        # Capa fuente neutral: Hermes refina la marca ya persiste por el
        # parser. Upsert por expediente (no borra lo demás del boletín).
        db.boletin_entry_upsert(conn, boletin_id, entry)

        # Buscar matches contra TODAS las watchlists activas (multi-tenant).
        # Regla AND: nombre (similitud ≥ fuzzy) + clase Niza igual +
        # distingue con intersección de tokens. Watchlists ``kind='titular'``
        # comparan el titular de la entry. Cap top-N por similitud para
        # evitar explosión (entradas alucinadas con muchas watchlists no
        # deben generar miles de detections).
        watch_candidates: list[tuple] = []
        for user in db.users_list(conn):
            user_watch = db.watchlist_list_for_user(conn, user.id, only_active=True)
            for w in user_watch:
                if w.kind == "titular":
                    if watch_titular_matches(w, entry):
                        watch_candidates.append((1.0, user.id, w, None))
                    continue
                name_sim = watch_entry_matches(w, entry, thresholds)
                if name_sim is not None:
                    watch_candidates.append((name_sim.name_sim, user.id, w, name_sim))

        watch_candidates.sort(key=lambda t: t[0], reverse=True)
        for _sim, user_id, w, name_sim in watch_candidates[:_MAX_MATCHES_PER_ENTRY]:
            if w.kind == "titular":
                similarity, confidence, matched_with = 1.0, "high", f"titular:{w.name}"
            else:
                similarity = name_sim.name_sim if name_sim is not None else 0.0
                confidence = "high" if similarity >= 0.95 else "medium"
                matched_with = w.name
            db.detections_add(
                conn,
                boletin_id=boletin_id,
                user_id=user_id,
                watchlist_id=w.id,
                mark_name=entry.marca,
                similarity=similarity,
                match_kind=(
                    "conflict"
                    if w.kind == "titular"
                    or (name_sim is not None and name_sim.is_family)
                    else "similar"
                ),
                risk_score=None,
                source=entry.fuente,
                confidence=confidence,
                matched_with=matched_with,
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
                disposicion=getattr(entry, "disposicion", None),
                tipo_disposicion=getattr(entry, "tipo_disposicion", None),
            )
            entries_added += 1

        # Match contra portafolios de TODOS los usuarios (multi-tenant)
        # por identidad (#registro / #solicitud) + filtro de nombre, y
        # conflicto/competencia (nombre + clase relacionada, excluyendo
        # al propio titular). Con la entry adaptada a duck-type.
        entry_like = _hermes_to_entry_like(entry)
        for user in db.users_list(conn):
            entries_added += match_portfolio_by_identity(
                conn,
                user.id,
                boletin_id,
                [entry_like],
                source=entry.fuente,
            )
            entries_added += match_portfolio_conflicts(
                conn,
                user.id,
                boletin_id,
                [entry_like],
                source=entry.fuente,
            )

    db.boletines_mark_hermes_progress_done(conn, boletin_id)
    conn.commit()
    return StructuredOut(boletin_id=boletin_id, status="processed", entries_added=entries_added)


@router.post("/{boletin_id}/hermes-progress", response_model=HermesProgressOut)
async def submit_hermes_progress(
    boletin_id: int,
    payload: HermesProgressIn,
    conn: sqlite3.Connection = Depends(get_db),
    _hermes: None = Depends(require_hermes),
):
    """Hermes reporta su avance página a página mientras analiza el boletín.

    Permite a la UI mostrar una barra de progreso real en vez de solo
    "en cola". El boletín debe estar ``extracted`` con ``needs_hermes_review=1``
    y aún sin ``hermes_processed_at``.
    """
    boletin = db.boletines_get(conn, boletin_id)
    if boletin is None:
        raise HTTPException(status_code=404, detail="Boletín no encontrado")
    if boletin.hermes_processed_at:
        raise HTTPException(
            status_code=409, detail="Boletín ya procesado por Hermes"
        )
    db.boletines_update_hermes_progress(
        conn,
        boletin_id,
        step=payload.step,
        current_page=payload.current_page,
        total_pages=payload.total_pages,
    )
    conn.commit()
    b = db.boletines_get(conn, boletin_id)
    return HermesProgressOut(
        boletin_id=boletin_id,
        step=b.hermes_progress_step,
        current_page=b.hermes_progress_current_page,
        total_pages=b.hermes_progress_total_pages,
        updated_at=b.hermes_progress_updated_at,
    )


@router.post("/{boletin_id}/hermes-done", response_model=HermesDoneOut)
async def mark_hermes_done(
    boletin_id: int,
    payload: HermesDoneIn,
    conn: sqlite3.Connection = Depends(get_db),
    _hermes: None = Depends(require_hermes),
):
    """Hermes concluye el análisis de un boletín sin entregar entries.

    Se usa cuando el agente determina que el boletín **no requiere visión**
    (texto confiable que el parser Python ya cubrió) o cuando ya completó el
    análisis página a página sin entradas nuevas. Marca ``hermes_processed_at``
    y ``hermes_progress_step='done'``, de modo que el boletín sale de la cola
    de revisión visual y no vuelve a procesarse. Idempotente.
    """
    boletin = db.boletines_get(conn, boletin_id)
    if boletin is None:
        raise HTTPException(status_code=404, detail="Boletín no encontrado")
    if payload.boletin_id != boletin_id:
        raise HTTPException(status_code=400, detail="boletin_id mismatch")
    if boletin.hermes_processed_at:
        return HermesDoneOut(
            boletin_id=boletin_id,
            status="already_processed",
            entries_added=0,
        )
    if payload.entries_added:
        db.boletines_update_hermes_progress(
            conn,
            boletin_id,
            step="done",
            current_page=boletin.hermes_progress_total_pages or boletin.hermes_progress_current_page,
        )
    db.boletines_mark_hermes_progress_done(conn, boletin_id)
    conn.commit()
    return HermesDoneOut(
        boletin_id=boletin_id,
        status="processed",
        entries_added=int(payload.entries_added or 0),
    )

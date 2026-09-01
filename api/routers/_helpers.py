"""Helpers para convertir Row dataclasses de db.py → Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from scripts import db
from scripts.schemas import (
    BoletinOut,
    DetectionOut,
    PortfolioHistoryOut,
    PortfolioOut,
    UserOut,
    WatchlistOut,
)


def user_to_out(r: db.UserRow) -> UserOut:
    return UserOut(
        id=r.id,
        email=r.email,
        role=r.role,
        active=bool(r.active),
        created_at=r.created_at,
    )


def watchlist_to_out(r: db.WatchlistRow) -> WatchlistOut:
    return WatchlistOut(
        id=r.id,
        user_id=r.user_id,
        name=r.name,
        class_nice=r.class_nice,
        notes=r.notes,
        active=bool(r.active),
        created_at=r.created_at,
    )


def portfolio_to_out(r: db.PortfolioRow) -> PortfolioOut:
    return PortfolioOut(
        id=r.id,
        user_id=r.user_id,
        name=r.name,
        expediente=r.expediente,
        class_nice=r.class_nice,
        status=r.status,
        last_checked_at=_parse_dt(r.last_checked_at),
        notes=r.notes,
        pais=r.pais,
        etiqueta=r.etiqueta,
        tipo_registro=r.tipo_registro,
        bufete=r.bufete,
        solicitud=r.solicitud,
        fecha_solicitud=r.fecha_solicitud,
        registro=r.registro,
        fecha_registro=r.fecha_registro,
        fecha_vencimiento=r.fecha_vencimiento,
        titular=r.titular,
        tramitante=r.tramitante,
        empresa_licenciada=r.empresa_licenciada,
        productos_servicios=r.productos_servicios,
        comentarios=r.comentarios,
        last_boletin_id=r.last_boletin_id,
        last_boletin_period=r.last_boletin_period,
        created_at=r.created_at,
        updated_at=_parse_dt(getattr(r, "updated_at", None)),
    )


def history_to_out(r: db.PortfolioHistoryRow) -> PortfolioHistoryOut:
    return PortfolioHistoryOut(
        id=r.id,
        portfolio_id=r.portfolio_id,
        user_id=r.user_id,
        boletin_id=r.boletin_id,
        boletin_period=r.boletin_period,
        boletin_number=r.boletin_number,
        estado=r.estado,
        snapshot=r.snapshot,
        created_at=_parse_dt(r.created_at),
    )


def boletin_to_out(r: db.BoletinRow) -> BoletinOut:
    return BoletinOut(
        id=r.id,
        uploaded_by=r.uploaded_by,
        filename=r.filename,
        file_path=r.file_path,
        file_sha256=r.file_sha256,
        bulletin_number=r.bulletin_number,
        period=r.period,
        pages=r.pages,
        status=r.status,
        needs_hermes_review=bool(r.needs_hermes_review),
        hermes_processed_at=_parse_dt(getattr(r, "hermes_processed_at", None)),
        uploaded_at=_parse_dt(r.uploaded_at) or datetime.now(),
        processed_at=_parse_dt(r.processed_at),
        error=r.error,
        entries_matcheables=r.entries_matcheables,
        entries_hermes_pending=r.entries_hermes_pending,
        entries_figura=r.entries_figura,
        entries_lema=r.entries_lema,
        progress_step=getattr(r, "progress_step", None),
        progress_current_page=getattr(r, "progress_current_page", None),
        progress_total_pages=getattr(r, "progress_total_pages", None),
    )


def detection_to_out(r: db.DetectionRow) -> DetectionOut:
    return DetectionOut(
        id=r.id,
        boletin_id=r.boletin_id,
        user_id=r.user_id,
        watchlist_id=r.watchlist_id,
        portfolio_id=r.portfolio_id,
        expediente=r.expediente,
        mark_name=r.mark_name,
        titular=r.titular,
        class_nice=r.class_nice,
        page=r.page,
        similarity=r.similarity,
        match_kind=r.match_kind,
        source=r.source,
        confidence=r.confidence,
        raw_excerpt=r.raw_excerpt,
        detected_at=r.detected_at,
        notified_email=bool(r.notified_email),
        pais=r.pais,
        fecha_inscripcion=r.fecha_inscripcion,
        fuente_parsing=r.fuente_parsing,
        es_figura=bool(r.es_figura),
        es_lema=bool(r.es_lema),
        needs_hermes_reverify=bool(getattr(r, "needs_hermes_reverify", 0)),
    )


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if val is None:
        return None
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None

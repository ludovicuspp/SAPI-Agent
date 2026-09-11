"""Acceso read-only a la BD de SAPI-Agent.

Solo lectura (nunca escribe): la skill orquesta y delega la escritura
a la API (POST /api/boletines/{id}/structured). Hermes no debe escribir
en SQLite jamás; si se requiere una modificación, va vía la API.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _bootstrap import setup_paths

setup_paths()  # idempotente; permite ejecución directa o import como módulo


def connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Abre la BD en modo read-only (URI ``file:...?mode=ro``)."""
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@dataclass
class HermesPendingInfo:
    """Resumen de un boletín pendiente de revisión visual."""

    boletin_id: int
    filename: str
    file_path: str
    pages: int
    total_pages: int
    needs_review_pages: int
    pages_with_images: int
    pages_low_confidence: int
    extraction_json: dict[str, Any]


def _page_flags_from_payload(payload: dict[str, Any]) -> tuple[int, int, int]:
    """Cuenta páginas marcadas a partir del ``extraction_json``.

    Devuelve ``(total_pages, pages_with_images, pages_low_confidence)``.
    """
    pages = payload.get("pages", [])
    images = sum(1 for p in pages if p.get("has_images"))
    low_confidence = sum(1 for p in pages if p.get("low_confidence"))
    return len(pages), images, low_confidence


def list_pending_hermes(db_path: str | Path, limit: int = 50) -> list[HermesPendingInfo]:
    """Lista boletines con ``needs_hermes_review=1`` aún sin procesar por Hermes.

    Mapea en SQL lo que hace ``scripts.db.boletines_list_pending_hermes``,
    pero devolviendo el ``extraction_json`` ya parseado (que es lo que la
    skill necesita para decidir qué páginas revisar).
    """
    with connect_readonly(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM boletines"
            " WHERE needs_hermes_review = 1"
            "   AND hermes_processed_at IS NULL"
            "   AND status IN ('extracted', 'hermes_pending')"
            " ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()

    result: list[HermesPendingInfo] = []
    for row in rows:
        payload = json.loads(row["extraction_json"] or "{}")
        total, images, low_conf = _page_flags_from_payload(payload)
        result.append(
            HermesPendingInfo(
                boletin_id=row["id"],
                filename=row["filename"],
                file_path=row["file_path"],
                pages=row["pages"] or 0,
                total_pages=total,
                needs_review_pages=images + low_conf,
                pages_with_images=images,
                pages_low_confidence=low_conf,
                extraction_json=payload,
            )
        )
    return result


@dataclass
class VerifyQueueItem:
    """Candidato a verificación de conflicto (Fase 4)."""

    id: int
    boletin_id: int
    user_id: int
    boletin_number: str | None
    boletin_filename: str | None
    boletin_period: str | None
    watchlist_id: int | None
    portfolio_id: int | None
    expediente: str | None
    mark_name: str
    matched_with: str | None
    titular: str | None
    class_nice: int | None
    page: int | None
    similarity: float
    match_kind: str
    confidence: str
    risk_score: float | None
    raw_excerpt: str | None
    detected_at: str


def list_verify_queue(db_path: str | Path, limit: int = 50) -> list[VerifyQueueItem]:
    """Lista detecciones pendientes de verificación Hermes (solo lectura).

    Mismo contrato que ``GET /api/detections/verify-queue``: detecciones
    con ``needs_hermes_reverify=1`` y sin veredicto, con contexto del
    boletín. Si la BD aún no tiene las columnas de Fase 4, devuelve ``[]``
    (el endpoint de veredicto la migra al arrancar el servicio).
    """
    with connect_readonly(db_path) as conn:
        try:
            rows = conn.execute(
                "SELECT d.id, d.boletin_id, d.user_id,"
                " d.watchlist_id, d.portfolio_id, d.expediente,"
                " d.mark_name, d.matched_with, d.titular, d.class_nice,"
                " d.page, d.similarity, d.match_kind, d.confidence,"
                " d.risk_score, d.raw_excerpt, d.detected_at,"
                " b.bulletin_number AS boletin_number,"
                " b.period AS boletin_period,"
                " b.filename AS boletin_filename"
                " FROM detections d"
                " JOIN boletines b ON b.id = d.boletin_id"
                " WHERE d.needs_hermes_reverify = 1"
                "   AND d.hermes_verdict IS NULL"
                " ORDER BY d.detected_at ASC, d.id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [VerifyQueueItem(**dict(r)) for r in rows]


def get_page_texts(db_path: str | Path, boletin_id: int) -> list[dict[str, Any]]:
    """Devuelve la lista de páginas del ``extraction_json`` de un boletín."""
    with connect_readonly(db_path) as conn:
        row = conn.execute(
            "SELECT extraction_json FROM boletines WHERE id = ?", (boletin_id,)
        ).fetchone()
    if row is None:
        return []
    payload = json.loads(row["extraction_json"] or "{}")
    return payload.get("pages", [])

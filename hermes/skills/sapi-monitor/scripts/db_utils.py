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

"""Pipeline end-to-end: PDF → boletin row + extraction_json + detections.

Responsabilidades:
- Calcular hash del PDF, crear fila en ``boletines``.
- Extraer texto con pdfplumber (``scripts.extractors.pdf_text``).
- Auto-detectar metadatos del boletín (``parsers.boletin_header``).
- Parsear entradas de marcas (``parsers.marca_entry``).
- Marcar ``needs_hermes_review=1`` si hay páginas con imágenes o
  con texto poco confiable (la visión multimodal de Hermes las
  procesará en Fase 5).
- Comparar entradas contra la watchlist y portafolio del usuario
  con el motor de matching.
- Persistir ``detections`` y ``scans_log``.
- (Opcional) notificar por email las nuevas detections.

Las decisiones de matching las toma SIEMPRE el motor Python
(``scripts.matcher.combined``). Nunca se delega a un LLM.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from scripts.config import Settings, get_settings
from scripts.db import (
    BoletinRow,
    DetectionRow,
    boletines_create,
    boletines_get,
    boletines_mark_extracted,
    boletines_mark_failed,
    detections_add,
    detections_mark_notified,
    detections_pending_notification,
    portfolio_list_for_user,
    portfolio_update_status,
    scans_log_record,
    watchlist_list_for_user,
)
from scripts.extractors import pdf_meta, pdf_text
from scripts.matcher import combined
from scripts.notifiers import email_smtp
from scripts.parsers import boletin_header, marca_entry


# ── Resultado del pipeline ─────────────────────────────────────


@dataclass
class ProcessResult:
    boletin_id: int
    filename: str
    bulletin_number: Optional[int]
    period: Optional[str]
    needs_hermes_review: bool
    pages_extracted: int
    pages_total: int
    entries_parsed: int
    detections_created: int
    emailed: int
    email_failed: int
    duration_ms: int


# ── Concatenación del texto para parsers ───────────────────────


def _build_parser_text(pages: list) -> str:
    """Une el texto de cada página con un marcador que ``marca_entry``
    usa para atribuir ``page`` a cada entrada detectada.
    """
    parts = []
    for p in pages:
        parts.append(f"--- página {p.page_number} ---")
        parts.append(p.text)
    return "\n".join(parts)


# ── Pipeline principal ─────────────────────────────────────────


def process_pdf(
    pdf_path: Path,
    *,
    user_id: int,
    conn: sqlite3.Connection,
    settings: Settings | None = None,
    notify: bool = False,
) -> ProcessResult:
    """Procesa un PDF end-to-end. Retorna un ``ProcessResult``.

    Lanza ``FileNotFoundError`` si el PDF no existe. Si el pipeline
    falla a mitad, marca el boletín como ``failed`` con el mensaje
    de error y registra en ``scans_log``.
    """
    cfg = settings or get_settings()
    start = time.monotonic()

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"No existe el PDF: {pdf_path}")

    file_sha = pdf_meta.hash_file(pdf_path)
    filename = pdf_path.name

    boletin_id = boletines_create(
        conn,
        uploaded_by=user_id,
        filename=filename,
        file_path=str(pdf_path),
        file_sha256=file_sha,
    )

    try:
        extraction = pdf_text.extract(pdf_path)
        pages_total = pdf_meta.count_pages(pdf_path)

        parser_text = _build_parser_text(extraction.pages)
        metadata = boletin_header.detect(parser_text)
        entries = marca_entry.parse(parser_text)

        needs_hermes = any(
            p.has_images or p.low_confidence for p in extraction.pages
        )

        extraction_payload = {
            "pages": [
                {
                    "page_number": p.page_number,
                    "text": p.text,
                    "char_count": p.char_count,
                    "has_images": p.has_images,
                    "low_confidence": p.low_confidence,
                }
                for p in extraction.pages
            ],
            "metadata": {
                "bulletin_number": metadata.bulletin_number,
                "period": metadata.period,
                "tomo": metadata.tomo,
            },
        }

        boletines_mark_extracted(
            conn,
            boletin_id=boletin_id,
            pages=pages_total,
            extraction_payload=extraction_payload,
            bulletin_number=metadata.bulletin_number,
            period=metadata.period,
            needs_hermes_review=needs_hermes,
        )

        # ── Match contra watchlist ───────────────────────────
        watch = watchlist_list_for_user(conn, user_id, only_active=True)
        watch_names = [w.name for w in watch]
        candidate_names = [e.marca for e in entries if e.marca]
        thresholds = combined.Thresholds.from_settings(
            cfg.match_threshold, cfg.fuzzy_threshold
        )

        detections_created = 0

        # Matching con watchlist: marca detectada en boletín vs watchlist
        match_pairs = combined.find_matches(
            watch_names, candidate_names, thresholds
        )
        # Indexa entradas por nombre para enriquecer expediente/titular/etc.
        entries_by_name: dict[str, marca_entry.MarcaEntry] = {}
        for e in entries:
            if e.marca and e.marca not in entries_by_name:
                entries_by_name[e.marca] = e

        watch_by_name = {w.name: w for w in watch}

        for watch_name, candidate, mr in match_pairs:
            entry = entries_by_name.get(candidate)
            if not entry:
                continue
            w = watch_by_name.get(watch_name)
            if not w:
                continue
            detections_add(
                conn,
                boletin_id=boletin_id,
                user_id=user_id,
                watchlist_id=w.id,
                mark_name=candidate,
                similarity=mr.similarity,
                match_kind="similar",
                source="pdfplumber_text",
                confidence=mr.confidence,
                expediente=entry.expediente,
                titular=entry.titular,
                class_nice=entry.clase_niza,
                page=entry.page,
                raw_excerpt=entry.excerpt,
            )
            detections_created += 1

        # ── Match contra portafolio propio (status update) ────
        portfolio = portfolio_list_for_user(conn, user_id)
        for entry in entries:
            if not entry.expediente:
                continue
            for p in portfolio:
                if p.expediente and p.expediente.strip() == entry.expediente.strip():
                    detections_add(
                        conn,
                        boletin_id=boletin_id,
                        user_id=user_id,
                        portfolio_id=p.id,
                        mark_name=entry.marca or "",
                        similarity=1.0,
                        match_kind="own_status",
                        source="pdfplumber_text",
                        confidence="high",
                        expediente=entry.expediente,
                        titular=entry.titular,
                        class_nice=entry.clase_niza,
                        page=entry.page,
                        raw_excerpt=entry.excerpt,
                    )
                    detections_created += 1
                    if entry.estatus:
                        portfolio_update_status(
                            conn, p.id, entry.estatus, user_id
                        )

        # ── Notificación por email (opcional) ─────────────────
        emailed = 0
        email_failed = 0
        if notify:
            user_row = conn.execute(
                "SELECT email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if user_row:
                pending = detections_pending_notification(conn, user_id)
                # Solo las creadas en este boletín, para no re-notificar lo viejo.
                pending_this_run = [d for d in pending if d.boletin_id == boletin_id]
                if pending_this_run:
                    boletin = boletines_get(conn, boletin_id)
                    boletines_map = {boletin_id: boletin} if boletin else {}
                    delivery = email_smtp.send_detection_emails(
                        to_address=user_row["email"],
                        detections=pending_this_run,
                        boletines_by_id=boletines_map,
                        settings=cfg,
                    )
                    detections_mark_notified(conn, delivery.sent)
                    emailed = delivery.sent
                    email_failed = len(delivery.failed)

        duration_ms = int((time.monotonic() - start) * 1000)
        scans_log_record(
            conn,
            kind="extract",
            status="ok",
            user_id=user_id,
            boletin_id=boletin_id,
            summary=f"{len(entries)} entries, {detections_created} detections",
            duration_ms=duration_ms,
        )

        return ProcessResult(
            boletin_id=boletin_id,
            filename=filename,
            bulletin_number=metadata.bulletin_number,
            period=metadata.period,
            needs_hermes_review=needs_hermes,
            pages_extracted=len(extraction.pages),
            pages_total=pages_total,
            entries_parsed=len(entries),
            detections_created=detections_created,
            emailed=emailed,
            email_failed=email_failed,
            duration_ms=duration_ms,
        )

    except Exception as e:
        boletines_mark_failed(conn, boletin_id, str(e))
        scans_log_record(
            conn,
            kind="extract",
            status="error",
            user_id=user_id,
            boletin_id=boletin_id,
            detail=str(e),
        )
        raise


# ── Re-procesar pendientes de Hermes (preparado para Fase 3) ──


def list_boletines_pending_hermes(
    conn: sqlite3.Connection, limit: int = 50
) -> list[BoletinRow]:
    """Devuelve boletines con ``needs_hermes_review=1`` aún sin procesar."""
    from scripts.db import boletines_list_pending_hermes

    return boletines_list_pending_hermes(conn, limit)

"""Pipeline end-to-end: PDF → boletin row + extraction_json + detections.

Responsabilidades:
- Calcular hash del PDF, crear fila en ``boletines``.
- Extraer texto por lotes (``scripts.extractors.pdf_batch``) con
  PyMuPDF y memoria acotada; cada lote se libera para evitar OOM en
  boletines de 1000+ páginas.
- Persistir un checkpoint por lotes (DB + JSONL en disco) para poder
  reanudar una extracción interrumpida sin reprocesar los lotes previos.
- Auto-detectar metadatos del boletín (``parsers.boletin_header``).
- Parsear entradas de marcas con el parser multi-formato
  (``parsers.marca_entry.MarcaEntryParser``).
- Asignar estatus (PUBLICADA/CONCEDIDA/NEGADA/etc.) por sección detectada.
- Marcar ``needs_hermes_review=1`` si hay páginas con imágenes o
  con texto poco confiable (la visión multimodal de Hermes las
  procesará en Fase 5).
- Comparar entradas contra la watchlist y portafolio del usuario
  con el motor de matching (siempre Python, nunca LLM).
- Persistir ``detections`` y ``scans_log``.
- (Opcional) notificar por email las nuevas detections.
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
    boletines_save_checkpoint,
    boletines_update_progress,
    detections_add,
    detections_mark_notified,
    detections_pending_notification,
    scans_log_record,
    watchlist_list_for_user,
)
from scripts.extractors import pdf_meta, pdf_batch
from scripts.matcher import combined
from scripts.notifiers import email_smtp
from scripts.orchestration.portfolio_sync import verify_entries_for_user
from scripts.parsers import boletin_header
from scripts.parsers.marca_entry import MarcaEntryParser, MarcaEntry, ParseStats


# ── Resultado del pipeline ─────────────────────────────────────


@dataclass
class ProcessResult:
    boletin_id: int
    filename: str
    bulletin_number: Optional[int]
    period: Optional[str]
    tomo: Optional[str]
    needs_hermes_review: bool
    pages_extracted: int
    pages_total: int
    entries_parsed: int
    entries_matcheables: int
    entries_figura: int
    entries_lema: int
    entries_hermes_pending: int
    detections_created: int
    emailed: int
    email_failed: int
    duration_ms: int


# ── Checkpoint JSONL en disco ──────────────────────────────────


def _checkpoint_path(data_dir: Path, boletin_id: int) -> Path:
    """Ruta del JSONL que guarda las páginas ya extraídas.

    Una línea por página: ``{page_number, text, char_count,
    has_images, low_confidence}``. Se escribe de forma incremental y
    se lee al final para construir el texto del parser sin retener
    todo el PDF en RAM.
    """
    return data_dir / "checkpoints" / f"boletin_{boletin_id}.jsonl"


def _write_page_append(checkpoint: Path, page: dict) -> None:
    import json as _json

    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(page, ensure_ascii=False) + "\n")


def _load_checkpoint_pages(checkpoint: Path) -> list[dict]:
    """Lee todas las líneas del checkpoint (páginas ya extraídas)."""
    import json as _json

    if not checkpoint.exists():
        return []
    pages: list[dict] = []
    with checkpoint.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                pages.append(_json.loads(line))
            except ValueError:
                continue
    return pages


def _build_parser_text(pages: list) -> str:
    """Une el texto de cada página con un marcador que ``MarcaEntryParser``
    usa para atribuir ``page`` a cada entrada detectada.
    """
    parts = []
    for p in pages:
        parts.append(f"--- página {p['page_number']} ---")
        parts.append(p["text"])
    return "\n".join(parts)


# ── Pipeline principal ─────────────────────────────────────────


def process_pdf(
    pdf_path: Path,
    *,
    user_id: int,
    conn: sqlite3.Connection,
    settings: Settings | None = None,
    notify: bool = False,
    boletin_id: Optional[int] = None,
) -> ProcessResult:
    """Procesa un PDF end-to-end. Retorna un ``ProcessResult``.

    Lanza ``FileNotFoundError`` si el PDF no existe. Si el pipeline
    falla a mitad, marca el boletín como ``failed`` con el mensaje
    de error y registra en ``scans_log``.

    Si se pasa ``boletin_id``, reutiliza esa fila en lugar de crear
    una nueva (usado por ``/api/boletines/upload`` para no duplicar
    filas por el mismo SHA).
    """
    cfg = settings or get_settings()
    start = time.monotonic()
    batch_size = max(1, int(cfg.pdf_batch_size))

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"No existe el PDF: {pdf_path}")

    file_sha = pdf_meta.hash_file(pdf_path)
    filename = pdf_path.name

    if boletin_id is None:
        boletin_id = boletines_create(
            conn,
            uploaded_by=user_id,
            filename=filename,
            file_path=str(pdf_path),
            file_sha256=file_sha,
        )

    checkpoint = _checkpoint_path(cfg.data_dir, boletin_id)

    def _report_progress(
        step: str,
        current_page: Optional[int] = None,
        total_pages: Optional[int] = None,
    ) -> None:
        boletines_update_progress(
            conn,
            boletin_id,
            step=step,
            current_page=current_page,
            total_pages=total_pages,
        )
        conn.commit()

    try:
        _report_progress("extracting_text")

        def _on_page(page_no: int, total: int) -> None:
            boletines_update_progress(
                conn, boletin_id, current_page=page_no, total_pages=total
            )
            # commit por página: el WebSocket de progreso ve avance real.
            conn.commit()

        def _on_batch(pages, start_page: int, end_page: int) -> None:
            # Persistir cada página al checkpoint y liberar el texto.
            for pe in pages:
                _write_page_append(
                    checkpoint,
                    {
                        "page_number": pe.page_number,
                        "text": pe.text,
                        "char_count": pe.char_count,
                        "has_images": pe.has_images,
                        "low_confidence": pe.low_confidence,
                    },
                )
            running["last_page"] = end_page
            if any(p.has_images for p in pages):
                running["has_images"] = True
            if any(p.low_confidence for p in pages):
                running["low_confidence"] = True
            if any("(cid:" in (p.text or "") for p in pages):
                running["cid_encoding"] = True
            ck = dict(running)
            boletines_save_checkpoint(conn, boletin_id, batch=end_page, checkpoints=ck)
            conn.commit()

        running: dict = {
            "last_page": 0,
            "has_images": False,
            "low_confidence": False,
            "cid_encoding": False,
        }

        # Reanudar si ya existe un checkpoint de un run anterior.
        already_done = _load_checkpoint_pages(checkpoint)
        resume_from = 0
        if already_done:
            resume_from = max(p["page_number"] for p in already_done)

        # Extracción por lotes. Si hay checkpoints previos, las páginas
        # ya extraídas están en disco; se continúa desde la siguiente.
        extraction = pdf_batch.extract_pdf_in_batches_memory_efficient(
            pdf_path,
            batch_size=batch_size,
            start_page=resume_from + 1,
            on_page=_on_page,
            on_batch=_on_batch,
        )
        pages_total = extraction.total_pages

        # En modo memory_efficient no retenemos páginas; el texto queda
        # en el checkpoint JSONL. Leerlo para construir parser_text.
        parser_pages = _load_checkpoint_pages(checkpoint)
        # Como el checkpoint se reanuda desde resume_from y pudo haber un
        # lote fallido a mitad, garantizamos unicidad/orden por page_number.
        parser_pages.sort(key=lambda p: p["page_number"])

        _report_progress("parsing_entries", current_page=pages_total, total_pages=pages_total)

        # Metadata: se detecta del texto ya extraído (header al inicio).
        parser_text = _build_parser_text(parser_pages)
        metadata = boletin_header.detect(parser_text)

        # Parser multi-formato con lookup de página por posición.
        import re as _re

        def page_lookup(text: str, position: int) -> Optional[int]:
            page_re = _re.compile(r"--- página (\d+) ---")
            last = None
            for m in page_re.finditer(text[: max(0, position)]):
                last = int(m.group(1))
            return last

        def section_lookup(text: str, position: int) -> Optional[str]:
            return boletin_header.detect_current_section(text, position)

        parser = MarcaEntryParser(
            page_lookup=page_lookup, section_lookup=section_lookup,
        )
        entries, stats = parser.parse_with_stats(parser_text)

        needs_hermes = any(
            p.get("has_images") or p.get("low_confidence") for p in parser_pages
        )

        extraction_payload = {
            "pages": [
                {
                    "page_number": p["page_number"],
                    "text": p["text"],
                    "char_count": p["char_count"],
                    "has_images": p["has_images"],
                    "low_confidence": p["low_confidence"],
                }
                for p in parser_pages
            ],
            "metadata": {
                "bulletin_number": metadata.bulletin_number,
                "period": metadata.period,
                "tomo": metadata.tomo,
            },
            "parse_stats": {
                "total": stats.total_inscripciones,
                "matcheables": stats.entries_matcheables,
                "figura": stats.entries_figura,
                "lema": stats.entries_lema,
                "hermes_pending": stats.entries_hermes_pending,
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
            entries_matcheables=stats.entries_matcheables,
            entries_hermes_pending=stats.entries_hermes_pending,
            entries_figura=stats.entries_figura,
            entries_lema=stats.entries_lema,
        )

        # ── Match contra watchlist ───────────────────────────
        _report_progress("matching")
        watch = watchlist_list_for_user(conn, user_id, only_active=True)
        watch_names = [w.name for w in watch]

        # Solo entries matcheables participan en el matching.
        matcheable_entries = [e for e in entries if e.matcheable]
        candidate_names = [e.marca for e in matcheable_entries if e.marca]
        candidate_classes = [e.clase for e in matcheable_entries if e.marca]
        watch_classes = [w.class_nice for w in watch]
        thresholds = combined.Thresholds.from_settings(
            cfg.match_threshold, cfg.fuzzy_threshold
        )

        detections_created = 0

        # Indexar entries por nombre para enriquecer expediente/titular/etc.
        entries_by_name: dict[str, MarcaEntry] = {}
        for e in matcheable_entries:
            if e.marca and e.marca not in entries_by_name:
                entries_by_name[e.marca] = e

        watch_by_name = {w.name: w for w in watch}

        if watch_names and candidate_names:
            match_pairs = combined.find_matches(
                watch_names, candidate_names, thresholds,
                watch_class_nices=watch_classes,
                candidate_class_nices=candidate_classes,
            )
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
                    pais=entry.pais,
                    fecha_inscripcion=entry.fecha_inscripcion,
                    fuente_parsing=entry.fuente_parsing,
                    es_figura=1 if entry.es_figura else 0,
                    es_lema=1 if entry.es_lema else 0,
                )
                detections_created += 1

        # ── Match contra portafolio propio (regla temporal + historial) ──
        sync_result = verify_entries_for_user(
            conn,
            user_id,
            boletines_get(conn, boletin_id),
            entries,
            source="pdfplumber_text",
        )
        detections_created += sync_result.matched

        # ── Notificación por email (opcional) ─────────────────
        _report_progress("notifying")
        emailed = 0
        email_failed = 0
        if notify:
            user_row = conn.execute(
                "SELECT email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if user_row:
                pending = detections_pending_notification(conn, user_id)
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

        _report_progress("done", current_page=pages_total, total_pages=pages_total)
        duration_ms = int((time.monotonic() - start) * 1000)
        scans_log_record(
            conn,
            kind="extract",
            status="ok",
            user_id=user_id,
            boletin_id=boletin_id,
            summary=(
                f"{stats.total_inscripciones} entries "
                f"({stats.entries_matcheables} matcheables, "
                f"{stats.entries_figura} figura, "
                f"{stats.entries_lema} lema), "
                f"{detections_created} detections"
            ),
            duration_ms=duration_ms,
        )

        # Limpiar checkpoint en disco al terminar.
        try:
            checkpoint.unlink(missing_ok=True)
        except OSError:
            pass

        return ProcessResult(
            boletin_id=boletin_id,
            filename=filename,
            bulletin_number=metadata.bulletin_number,
            period=metadata.period,
            tomo=metadata.tomo,
            needs_hermes_review=needs_hermes,
            pages_extracted=len(parser_pages),
            pages_total=pages_total,
            entries_parsed=stats.total_inscripciones,
            entries_matcheables=stats.entries_matcheables,
            entries_figura=stats.entries_figura,
            entries_lema=stats.entries_lema,
            entries_hermes_pending=stats.entries_hermes_pending,
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

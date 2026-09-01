"""POST /api/boletines/upload — multipart + background task + WebSocket progreso."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
import sqlite3

from scripts import db
from scripts.config import get_settings, Settings
from scripts.orchestration import processor
from api.deps import get_db, get_current_user
from scripts.schemas import UploadOut

router = APIRouter()


_MAX_SPOOL_BYTES = 1024 * 1024  # 1 MB; chunks de lectura/escritura.


def _hash_and_write_stream(file: UploadFile, dest: Path) -> str:
    """Hashea y escribe el archivo por chunks. Devuelve el SHA-256 hex.

    Mantiene el uso de RAM acotado al tamaño del chunk, no al PDF
    completo.
    """
    sha = hashlib.sha256()
    with dest.open("wb") as fh:
        while True:
            chunk = file.file.read(_MAX_SPOOL_BYTES)
            if not chunk:
                break
            sha.update(chunk)
            fh.write(chunk)
    return sha.hexdigest()


def _process_boletin_task(boletin_id: int, pdf_path: str, user_id: int) -> None:
    """Background task: procesa el PDF completo en un thread separado."""
    cfg = Settings()
    conn = db.connect(cfg.sapi_db_path)
    try:
        processor.process_pdf(
            Path(pdf_path),
            user_id=user_id,
            conn=conn,
            settings=cfg,
            notify=False,
            boletin_id=boletin_id,
        )
        conn.commit()
    except Exception as e:
        try:
            db.boletines_mark_failed(conn, boletin_id, str(e))
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


@router.post("/upload", response_model=UploadOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_boletin(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    bulletin_number: int | None = Form(None),
    period: str | None = Form(None),
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    cfg = get_settings()
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    # Tamaño anunciado por Starlette (no incluye headers/boundary del multipart).
    # Si no está disponible, recurrimos a la cabecera Content-Length del part.
    size_hint = getattr(file, "size", None)
    max_bytes = cfg.max_upload_mb * 1024 * 1024
    if size_hint is not None and size_hint == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    if size_hint is not None and size_hint > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"PDF excede {cfg.max_upload_mb} MB",
        )

    # Hashear + escribir a disco por chunks. `file.file` es un
    # SpooledTemporaryFile; leerlo en trozos evita cargar el PDF
    # completo en RAM.
    await file.seek(0)
    upload_path = Path(cfg.uploads_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    tmp_path = upload_path / f".{file.filename}.part"
    try:
        sha = _hash_and_write_stream(file, tmp_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    final_size = tmp_path.stat().st_size
    if final_size == 0:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Archivo vacío")
    if final_size > max_bytes:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=f"PDF excede {cfg.max_upload_mb} MB",
        )

    final_path = upload_path / f"{sha}.pdf"
    tmp_path.rename(final_path)

    boletin_id = db.boletines_create(conn, user.id, file.filename, str(final_path), sha)
    background_tasks.add_task(_process_boletin_task, boletin_id, str(final_path), user.id)
    conn.commit()

    return UploadOut(boletin_id=boletin_id, status="extracting")


@router.websocket("/ws/{boletin_id}")
async def ws_progress(websocket: WebSocket, boletin_id: int) -> None:
    """WebSocket que envía eventos de progreso de un boletin_id."""
    await websocket.accept()
    cfg = get_settings()
    last_signature = None
    try:
        while True:
            conn = db.connect(cfg.sapi_db_path)
            try:
                b = db.boletines_get(conn, boletin_id)
                if b is None:
                    await websocket.send_json({"error": "not_found"})
                    break
                signature = (
                    b.status,
                    b.progress_step,
                    b.progress_current_page,
                    b.progress_total_pages,
                    b.pages,
                    b.entries_matcheables,
                    b.entries_figura,
                    b.entries_lema,
                    b.entries_hermes_pending,
                )
                if signature != last_signature:
                    await websocket.send_json({
                        "boletin_id": boletin_id,
                        "status": b.status,
                        "pages": b.pages,
                        "progress_step": b.progress_step,
                        "progress_current_page": b.progress_current_page,
                        "progress_total_pages": b.progress_total_pages,
                        "needs_hermes_review": bool(b.needs_hermes_review),
                        "hermes_processed_at": b.hermes_processed_at,
                        "entries_matcheables": b.entries_matcheables,
                        "entries_figura": b.entries_figura,
                        "entries_lema": b.entries_lema,
                        "entries_hermes_pending": b.entries_hermes_pending,
                        "error": b.error,
                    })
                    last_signature = signature
                if b.status in ("extracted", "failed"):
                    break
            finally:
                conn.close()
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass

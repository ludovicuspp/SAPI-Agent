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


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


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
    content = await file.read()
    if len(content) > cfg.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"PDF excede {cfg.max_upload_mb} MB")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    sha = _hash_bytes(content)
    upload_path = Path(cfg.uploads_dir) / f"{sha}.pdf"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(content)

    boletin_id = db.boletines_create(conn, user.id, file.filename, str(upload_path), sha)
    background_tasks.add_task(_process_boletin_task, boletin_id, str(upload_path), user.id)
    conn.commit()

    return UploadOut(boletin_id=boletin_id, status="extracting")


@router.websocket("/ws/{boletin_id}")
async def ws_progress(websocket: WebSocket, boletin_id: int) -> None:
    """WebSocket que envía eventos de progreso de un boletin_id."""
    await websocket.accept()
    cfg = get_settings()
    last_status = None
    try:
        while True:
            conn = db.connect(cfg.sapi_db_path)
            try:
                b = db.boletines_get(conn, boletin_id)
                if b is None:
                    await websocket.send_json({"error": "not_found"})
                    break
                if b.status != last_status:
                    await websocket.send_json({
                        "boletin_id": boletin_id,
                        "status": b.status,
                        "pages": b.pages,
                        "entries_matcheables": b.entries_matcheables,
                        "entries_figura": b.entries_figura,
                        "entries_lema": b.entries_lema,
                        "entries_hermes_pending": b.entries_hermes_pending,
                        "error": b.error,
                    })
                    last_status = b.status
                if b.status in ("extracted", "failed"):
                    break
            finally:
                conn.close()
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass

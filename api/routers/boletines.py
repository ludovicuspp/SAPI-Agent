"""GET /api/boletines — listado, detalle y borrado."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
import sqlite3

from scripts import db
from api.deps import get_db, get_current_user
from api.routers._helpers import boletin_to_out
from scripts.schemas import BoletinOut

router = APIRouter()


@router.get("", response_model=list[BoletinOut])
async def list_boletines(
    limit: int = 50,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    if user.role == "admin":
        rows = db.boletines_list_recent(conn, user_id=None, limit=limit)
    else:
        rows = db.boletines_list_recent(conn, user_id=user.id, limit=limit)
    return [boletin_to_out(r) for r in rows]


@router.get("/{boletin_id}", response_model=BoletinOut)
async def get_boletin(
    boletin_id: int,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    b = db.boletines_get(conn, boletin_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Boletín no encontrado")
    if user.role != "admin" and b.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Boletín no encontrado")
    return boletin_to_out(b)


@router.delete("/{boletin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_boletin(
    boletin_id: int,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Borra un boletín y sus detecciones.

    Permitido al usuario que lo subió (`uploaded_by`) o a cualquier
    admin. 409 si el boletín sigue procesándose o está en la cola de
    Hermes.
    """
    b = db.boletines_get(conn, boletin_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Boletín no encontrado")
    if user.role != "admin" and b.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Boletín no encontrado")

    in_hermes_queue = bool(
        b.needs_hermes_review and not b.hermes_processed_at
    )
    if b.status == "extracting" or in_hermes_queue:
        raise HTTPException(
            status_code=409,
            detail="El boletín se está procesando; espera a que termine",
        )

    file_path = Path(b.file_path)
    file_sha = b.file_sha256

    db.boletines_delete(conn, boletin_id)
    conn.commit()

    # Borrar el PDF solo si ningún otro boletín lo sigue usando.
    if file_path.is_file() and db.boletines_count_with_sha(conn, file_sha) == 0:
        try:
            file_path.unlink()
        except OSError:
            pass

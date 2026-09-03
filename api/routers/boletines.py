"""GET /api/boletines — listado, detalle y borrado."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
import sqlite3

from scripts import db
from api.deps import get_db, get_current_user
from api.routers._helpers import boletin_to_out
from scripts.schemas import BoletinEntryOut, BoletinOut

router = APIRouter()


@router.get("", response_model=list[BoletinOut])
async def list_boletines(
    limit: int = 50,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    # Multi-tenant: cada usuario solo ve los boletines que subió.
    # El admin ve todos.
    user_id = None if user.role == "admin" else user.id
    rows = db.boletines_list_recent(conn, user_id=user_id, limit=limit)
    return [boletin_to_out(r, conn) for r in rows]


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
    return boletin_to_out(b, conn)


def _entry_to_out(e: db.BoletinEntryRow) -> BoletinEntryOut:
    return BoletinEntryOut(
        id=e.id,
        boletin_id=e.boletin_id,
        expediente=e.expediente,
        marca=e.marca,
        class_nice=e.class_nice,
        clase_especial=e.clase_especial,
        titular=e.titular,
        pais=e.pais,
        fecha_inscripcion=e.fecha_inscripcion,
        estatus=e.estatus,
        page=e.page,
        is_matcheable=bool(e.is_matcheable),
        is_figura=bool(e.is_figura),
        is_lema=bool(e.is_lema),
        productos_servicios=e.productos_servicios,
        fuente_parsing=e.fuente_parsing,
        source=e.source,
        excerpt=e.excerpt,
    )


@router.get("/{boletin_id}/entries", response_model=list[BoletinEntryOut])
async def get_boletin_entries(
    boletin_id: int,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Devuelve las marcas extraídas de un boletín (capa fuente neutral).

    Misma visibilidad que el detalle: solo el dueño (`uploaded_by`) o un
    admin. A diferencia de ``detections``, aquí se listan TODAS las marcas
    del boletín, no solo las que matchean con una watchlist/portfolio.
    """
    b = db.boletines_get(conn, boletin_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Boletín no encontrado")
    if user.role != "admin" and b.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Boletín no encontrado")
    entries = db.boletines_entries_list(conn, boletin_id)
    return [_entry_to_out(e) for e in entries]


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

    # En cola o en proceso: NO se puede borrar (podría romper la extracción
    # o la tarea de Hermes en curso). Los boletines `failed` quedan exentos:
    # fallaron y no volverán a procesarse, así que el usuario debe poder
    # borrarlos para reintentar.
    deletable_terminal = b.status == "failed"
    in_hermes_queue = bool(
        not deletable_terminal
        and b.needs_hermes_review
        and not b.hermes_processed_at
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
    db.user_log_action(conn, user.id, f"eliminar_boletin:{boletin_id}")

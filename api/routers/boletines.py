"""GET /api/boletines — listado y detalle."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from scripts import db
from api.deps import get_db, get_current_user, require_admin
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

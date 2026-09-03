"""CRUD /api/watchlist — multi-tenant."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from scripts import db
from api.deps import get_db, get_current_user
from api.routers._helpers import run_retroactive_analysis, watchlist_to_out
from scripts.schemas import WatchlistIn, WatchlistOut

router = APIRouter()


@router.get("", response_model=list[WatchlistOut])
async def list_watchlist(
    only_active: bool = True,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    return [
        watchlist_to_out(r)
        for r in db.watchlist_list_for_user(conn, user.id, only_active=only_active)
    ]


@router.post("", response_model=WatchlistOut, status_code=201)
async def add_watchlist(
    body: WatchlistIn,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        wid = db.watchlist_add(
            conn,
            user.id,
            body.name,
            body.class_nice,
            body.notes,
            productos_servicios=body.productos_servicios,
        )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.user_log_action(conn, user.id, f"crear_watchlist:{body.name}")
    rows = db.watchlist_list_for_user(conn, user.id)
    row = next((r for r in rows if r.id == wid), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist no encontrada")
    run_retroactive_analysis(conn, user, f"watchlist:{body.name}")
    return watchlist_to_out(row)


@router.delete("/{watchlist_id}", status_code=204)
async def deactivate_watchlist(
    watchlist_id: int,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    db.watchlist_toggle(conn, watchlist_id, user.id, active=False)
    conn.commit()
    db.user_log_action(conn, user.id, f"desactivar_watchlist:{watchlist_id}")

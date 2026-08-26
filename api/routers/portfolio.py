"""CRUD /api/portfolio — multi-tenant."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from scripts import db
from api.deps import get_db, get_current_user
from api.routers._helpers import portfolio_to_out
from scripts.schemas import PortfolioIn, PortfolioOut

router = APIRouter()


@router.get("", response_model=list[PortfolioOut])
async def list_portfolio(
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    return [
        portfolio_to_out(r)
        for r in db.portfolio_list_for_user(conn, user.id)
    ]


@router.post("", response_model=PortfolioOut, status_code=201)
async def add_portfolio(
    body: PortfolioIn,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        pid = db.portfolio_add(
            conn, user.id, body.name, body.expediente, body.class_nice, body.notes,
        )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    rows = db.portfolio_list_for_user(conn, user.id)
    row = next((r for r in rows if r.id == pid), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio no encontrado")
    return portfolio_to_out(row)

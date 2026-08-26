"""GET /api/detections — listado con filtros, multi-tenant."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from scripts import db
from api.deps import get_db, get_current_user
from api.routers._helpers import detection_to_out
from scripts.schemas import DetectionOut

router = APIRouter()


@router.get("", response_model=list[DetectionOut])
async def list_detections(
    limit: int = 100,
    boletin_id: Optional[int] = None,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = db.detections_list_for_user(conn, user.id, limit=limit, boletin_id=boletin_id)
    return [detection_to_out(r) for r in rows]

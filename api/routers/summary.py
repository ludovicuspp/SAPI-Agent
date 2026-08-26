"""GET /api/summary — KPIs para el dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends
import sqlite3

from scripts import db
from api.deps import get_db, get_current_user
from api.routers._helpers import boletin_to_out, detection_to_out
from scripts.schemas import SummaryOut

router = APIRouter()


@router.get("", response_model=SummaryOut)
async def get_summary(
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    stats = db.stats_for_user(conn, user.id)
    recent_detections = db.detections_list_for_user(conn, user.id, limit=5)
    recent_boletines = db.boletines_list_recent(conn, user_id=user.id, limit=5)
    return SummaryOut(
        watchlist_count=stats.watchlist_count,
        portfolio_count=stats.portfolio_count,
        boletines_count=stats.boletines_count,
        detections_count=stats.detections_count,
        last_boletin_at=stats.last_boletin_at,
        recent_detections=[detection_to_out(d) for d in recent_detections],
        recent_boletines=[boletin_to_out(b) for b in recent_boletines],
    )

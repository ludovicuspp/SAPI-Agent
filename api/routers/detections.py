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


@router.post("/{detection_id}/reverify", response_model=DetectionOut)
async def reverify_with_hermes(
    detection_id: int,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Marca una detection como ``needs_hermes_reverify=1``.

    Cuando Hermes revise el boletín asociado, hará una pasada adicional
    con visión multimodal sobre esa detection específica para confirmar
    o descartar el match (defensa contra falsos positivos del script
    de extracción Python).

    Restricciones:
    - La detection pertenece al usuario actual (o es admin).
    - El boletín asociado tiene ``needs_hermes_review=1`` (de lo contrario,
      no hay nada que reverificar).
    """
    det = conn.execute(
        "SELECT * FROM detections WHERE id = ?", (detection_id,)
    ).fetchone()
    if det is None:
        raise HTTPException(status_code=404, detail="Detection no encontrada")
    if det["user_id"] != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="No autorizado")

    bol = db.boletines_get(conn, det["boletin_id"])
    if bol is None:
        raise HTTPException(status_code=404, detail="Boletín asociado no existe")
    if not bol.needs_hermes_review:
        raise HTTPException(
            status_code=400,
            detail="El boletín no requiere revisión Hermes; "
            "no hay nada que reverificar.",
        )

    conn.execute(
        "UPDATE detections SET needs_hermes_reverify = 1 WHERE id = ?",
        (detection_id,),
    )
    # Resetear hermes_processed_at para forzar que el cron de Hermes
    # vuelva a procesar este boletín (al menos una vez más).
    conn.execute(
        "UPDATE boletines SET hermes_processed_at = NULL WHERE id = ?",
        (det["boletin_id"],),
    )
    conn.commit()
    db.user_log_action(conn, user.id, f"reverificar_detection:{detection_id}")

    det2 = conn.execute(
        "SELECT * FROM detections WHERE id = ?", (detection_id,)
    ).fetchone()
    return detection_to_out(db._detection_from_row(det2))

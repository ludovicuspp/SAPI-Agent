"""GET/POST /api/alerts — lapsos legales por detección, multi-tenant.

Cada detección con tipo de disposición (o estatus PUBLIADA) abre una
alerta de lapso calculada en días hábiles desde ``boletines.fecha_publicacion``.
Los plazos son editables (solo admin) en ``lapse_config``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from scripts import db
from scripts.lapsos import derivar_estado, dias_restantes, rebuild_pending_for_config
from api.deps import get_db, get_current_user, require_admin
from api.routers._helpers import boletin_to_out
from scripts.schemas import (
    AlertEstado,
    AlertOut,
    AlertResolveIn,
    LapseConfigIn,
    LapseConfigOut,
)

router = APIRouter()


def _alert_to_out(
    conn: sqlite3.Connection, r: db.AlertRow
) -> AlertOut:
    bol = conn.execute(
        "SELECT bulletin_number, period, filename FROM boletines WHERE id = ?",
        (r.boletin_id,),
    ).fetchone()
    det = conn.execute(
        "SELECT match_kind, disposicion, tipo_disposicion"
        " FROM detections WHERE id = ?",
        (r.detection_id,),
    ).fetchone()
    return AlertOut(
        id=r.id,
        user_id=r.user_id,
        detection_id=r.detection_id,
        boletin_id=r.boletin_id,
        lapse_key=r.lapse_key,
        label=r.label,
        marca=r.marca,
        expediente=r.expediente,
        fecha_publicacion=r.fecha_publicacion,
        fecha_limite=r.fecha_limite,
        dias_habiles=r.dias_habiles,
        estado=derivar_estado(r),
        dias_restantes=dias_restantes(r),
        created_at=r.created_at,
        resolved_at=r.resolved_at,
        boletin_number=bol["bulletin_number"] if bol else None,
        boletin_period=bol["period"] if bol else None,
        boletin_filename=bol["filename"] if bol else None,
        match_kind=det["match_kind"] if det else None,
        disposicion=det["disposicion"] if det else None,
        tipo_disposicion=det["tipo_disposicion"] if det else None,
    )


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    estado: Optional[str] = None,
    boletin_id: Optional[int] = None,
    limit: int = 200,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = db.alerts_list_for_user(
        conn, user.id, estado=estado, boletin_id=boletin_id, limit=limit
    )
    return [_alert_to_out(conn, r) for r in rows]


@router.post("/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(
    alert_id: int,
    body: AlertResolveIn,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    alert = conn.execute(
        "SELECT * FROM alerts WHERE id = ?", (alert_id,)
    ).fetchone()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    if alert["user_id"] != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="No autorizado")
    row = db.alerts_resolve(
        conn, alert_id, user_id=alert["user_id"], estado=body.estado
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    conn.commit()
    db.user_log_action(
        conn,
        user.id,
        f"alerta:{alert_id}:{body.estado}:{row.lapse_key}:{row.marca or row.expediente}",
    )
    return _alert_to_out(conn, row)


@router.get("/config", response_model=list[LapseConfigOut])
async def list_lapse_config(
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    return [
        LapseConfigOut(
            key=r.key,
            label=r.label,
            dias_habiles=r.dias_habiles,
            default_dias_habiles=r.default_dias_habiles,
        )
        for r in db.lapse_config_list(conn)
    ]


@router.put("/config/{key}", response_model=LapseConfigOut)
async def update_lapse_config(
    key: str,
    body: LapseConfigIn,
    admin: db.UserRow = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
):
    cfg = db.lapse_config_get(conn, key)
    if cfg is None:
        raise HTTPException(
            status_code=404, detail=f"Lapso no reconocido: {key}"
        )
    db.lapse_config_update(conn, key, dias_habiles=body.dias_habiles)
    # Recalcula las alertas pendientes con el nuevo plazo (las resueltas
    # conservan su fecha histórica).
    rebuilt = rebuild_pending_for_config(conn)
    conn.commit()
    db.user_log_action(
        conn, admin.id, f"lapse_config:{key}:{body.dias_habiles}:{rebuilt} rebuilt"
    )
    cfg = db.lapse_config_get(conn, key)
    return LapseConfigOut(
        key=cfg.key,
        label=cfg.label,
        dias_habiles=cfg.dias_habiles,
        default_dias_habiles=cfg.default_dias_habiles,
    )
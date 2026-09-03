"""CRUD /api/portfolio — multi-tenant.

Incluye: alta/listado/detalle/edición de marcas, carga de etiqueta
(PNG/JPG), historial de la marca, plantilla descargable e importación
masiva CSV.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
import sqlite3

from scripts import db
from scripts import portfolio_import
from scripts.config import get_settings
from api.deps import get_db, get_current_user
from api.routers._helpers import (
    history_to_out,
    portfolio_to_out,
    run_retroactive_analysis,
)
from scripts.schemas import (
    PortfolioHistoryOut,
    PortfolioImportResult,
    PortfolioIn,
    PortfolioOut,
)

router = APIRouter()

_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def _get_owned(
    conn: sqlite3.Connection, portfolio_id: int, user: db.UserRow
) -> db.PortfolioRow:
    row = db.portfolio_get(conn, portfolio_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio no encontrado")
    return row


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
            conn,
            user_id=user.id,
            name=body.name,
            expediente=body.expediente,
            class_nice=body.class_nice,
            notes=body.notes,
            pais=body.pais,
            etiqueta=body.etiqueta,
            tipo_registro=body.tipo_registro,
            bufete=body.bufete,
            solicitud=body.solicitud,
            fecha_solicitud=body.fecha_solicitud,
            registro=body.registro,
            fecha_registro=body.fecha_registro,
            fecha_vencimiento=body.fecha_vencimiento,
            titular=body.titular,
            tramitante=body.tramitante,
            empresa_licenciada=body.empresa_licenciada,
            productos_servicios=body.productos_servicios,
            comentarios=body.comentarios,
            status=body.status,
        )
        conn.commit()
        db.user_log_action(conn, user.id, f"crear_portfolio:{body.name}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    row = db.portfolio_get(conn, pid, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio no encontrado")
    run_retroactive_analysis(conn, user.id, f"portfolio:{body.name}")
    return portfolio_to_out(row)


@router.get("/template", response_class=PlainTextResponse)
async def download_template(
    user: db.UserRow = Depends(get_current_user),
):
    """Plantilla CSV para importación masiva."""
    csv_text = portfolio_import.render_template()
    return PlainTextResponse(
        csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=portfolio_template.csv"},
    )


@router.post("/import", response_model=PortfolioImportResult)
async def import_portfolio(
    file: UploadFile,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Importa marcas desde CSV (separador ``;``, plantilla del sistema)."""
    content = await file.read()
    rows, errors = portfolio_import.parse_import(content)
    if errors:
        return PortfolioImportResult(created=0, updated=0, errors=errors[:50])
    result = portfolio_import.apply_import(conn, user.id, rows)
    conn.commit()
    if result.created:
        run_retroactive_analysis(conn, user.id, "import_portfolio")
    return PortfolioImportResult(
        created=result.created,
        updated=result.updated,
        errors=result.errors[:50],
    )


@router.get("/{portfolio_id}", response_model=PortfolioOut)
async def get_portfolio(
    portfolio_id: int,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = _get_owned(conn, portfolio_id, user)
    return portfolio_to_out(row)


@router.put("/{portfolio_id}", response_model=PortfolioOut)
async def update_portfolio(
    portfolio_id: int,
    body: PortfolioIn,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    _get_owned(conn, portfolio_id, user)
    fields = {
        "name": body.name,
        "expediente": body.expediente,
        "class_nice": body.class_nice,
        "notes": body.notes,
        "pais": body.pais,
        "etiqueta": body.etiqueta,
        "tipo_registro": body.tipo_registro,
        "bufete": body.bufete,
        "solicitud": body.solicitud,
        "fecha_solicitud": body.fecha_solicitud,
        "registro": body.registro,
        "fecha_registro": body.fecha_registro,
        "fecha_vencimiento": body.fecha_vencimiento,
        "titular": body.titular,
        "tramitante": body.tramitante,
        "empresa_licenciada": body.empresa_licenciada,
        "productos_servicios": body.productos_servicios,
        "comentarios": body.comentarios,
        "status": body.status,
    }
    db.portfolio_update(conn, portfolio_id, user.id, **fields)
    conn.commit()
    row = db.portfolio_get(conn, portfolio_id, user_id=user.id)
    return portfolio_to_out(row)


@router.post("/{portfolio_id}/etiqueta", response_model=PortfolioOut)
async def upload_etiqueta(
    portfolio_id: int,
    file: UploadFile,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Sube la etiqueta (PNG/JPG) de la marca a ``data/uploads/etiquetas``."""
    _get_owned(conn, portfolio_id, user)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=400,
            detail="La etiqueta debe ser PNG o JPG.",
        )
    cfg = get_settings()
    etiquetas_dir = cfg.data_dir / "uploads" / "etiquetas"
    etiquetas_dir.mkdir(parents=True, exist_ok=True)
    dest = etiquetas_dir / f"p{portfolio_id}{ext}"
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    dest.write_bytes(content)
    etiqueta_url = f"/uploads/etiquetas/{dest.name}"
    db.portfolio_update(conn, portfolio_id, user.id, etiqueta=etiqueta_url)
    conn.commit()
    row = db.portfolio_get(conn, portfolio_id, user_id=user.id)
    return portfolio_to_out(row)


@router.get("/{portfolio_id}/history", response_model=list[PortfolioHistoryOut])
async def portfolio_history(
    portfolio_id: int,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Historial de la marca (solo lectura): boletín + snapshot completo."""
    _get_owned(conn, portfolio_id, user)
    return [
        history_to_out(h)
        for h in db.portfolio_history_list(conn, portfolio_id, user.id)
    ]
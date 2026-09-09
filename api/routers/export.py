"""GET /api/export/{dataset}.{fmt} — descarga de datos en .csv y .md.

Datasets: detections, portfolio, watchlist. Formatos: csv, md.

Misma semántica multi-tenant que los endpoints de listado: cada usuario
exporta lo suyo (el admin también ve lo propio aquí; el monitoreo global
está en /api/admin/metrics y en la UI de monitoreo).
"""
from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from scripts import db
from api.deps import get_db, get_current_user
from api.routers._helpers import detection_to_out

router = APIRouter()

_EXPORT_LIMIT = 10000


def _csv_response(rows: list[list[str]], headers: list[str], name: str) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    # utf-8-sig: BOM para que Excel en locales hispanos abra el CSV bien.
    content = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="sapi-{name}.csv"'},
    )


def _md_escape(v: str) -> str:
    return v.replace("|", "\\|").replace("\n", " ")


def _md_response(
    rows: list[list[str]], headers: list[str], name: str, title: str
) -> Response:
    lines = [
        f"# {title}",
        "",
        f"_Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')} por SAPI-Agent._",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(_md_escape(c) for c in row) + " |" for row in rows)
    content = ("\n".join(lines) + "\n").encode("utf-8")
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="sapi-{name}.md"'},
    )


def _s(v) -> str:
    return "" if v is None else str(v)


def _build_detections(conn: sqlite3.Connection, user: db.UserRow):
    headers = [
        "Fecha", "Boletín", "Expediente", "Marca", "Titular", "Clase",
        "Similitud", "Riesgo", "Match con", "Tipo", "Fuente", "Página", "País",
    ]
    rows = db.detections_list_for_user(conn, user.id, limit=_EXPORT_LIMIT)
    out = []
    for d in rows:
        o = detection_to_out(d)
        out.append([
            o.detected_at.strftime("%Y-%m-%d %H:%M"),
            str(o.boletin_id),
            _s(o.expediente),
            o.mark_name,
            _s(o.titular),
            _s(o.class_nice),
            f"{o.similarity:.2f}",
            _s(o.risk_score),
            _s(o.matched_with),
            o.match_kind,
            o.source,
            _s(o.page),
            _s(o.pais),
        ])
    return headers, out, "detecciones"


def _build_portfolio(conn: sqlite3.Connection, user: db.UserRow):
    headers = [
        "Marca", "Estado", "Expediente", "Clase", "Titular", "Tramitante",
        "Bufete", "País", "Etiqueta", "Tipo", "#Solicitud", "F. Solicitud",
        "#Registro", "F. Registro", "F. Vencimiento", "Empresa licenciada",
        "Productos/Servicios", "Comentarios",
    ]
    rows = db.portfolio_list_for_user(conn, user.id)
    out = []
    for p in rows:
        out.append([
            p.name, _s(p.status), _s(p.expediente), _s(p.class_nice),
            _s(p.titular), _s(p.tramitante), _s(p.bufete), _s(p.pais),
            _s(p.etiqueta), _s(p.tipo_registro), _s(p.solicitud),
            _s(p.fecha_solicitud), _s(p.registro), _s(p.fecha_registro),
            _s(p.fecha_vencimiento), _s(p.empresa_licenciada),
            _s(p.productos_servicios), _s(p.comentarios),
        ])
    return headers, out, "portafolio"


def _build_watchlist(conn: sqlite3.Connection, user: db.UserRow):
    headers = [
        "Marca", "Tipo", "Clase", "Productos/Servicios", "Familia",
        "Notas", "Activa",
    ]
    rows = db.watchlist_list_for_user(conn, user.id)
    out = []
    for w in rows:
        out.append([
            w.name, _s(w.kind), _s(w.class_nice),
            _s(w.productos_servicios),
            "sí" if w.match_family else "no",
            _s(w.notes),
            "sí" if w.active else "no",
        ])
    return headers, out, "watchlist"


_BUILDERS: dict[str, tuple[Callable, str]] = {
    "detections": (_build_detections, "Detecciones SAPI"),
    "portfolio": (_build_portfolio, "Portafolio SAPI"),
    "watchlist": (_build_watchlist, "Watchlist SAPI"),
}


@router.get("/{dataset}.{fmt}")
async def export_dataset(
    dataset: str,
    fmt: str,
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Descarga ``detections`` / ``portfolio`` / ``watchlist`` como .csv o .md."""
    builder = _BUILDERS.get(dataset)
    if builder is None:
        raise HTTPException(
            status_code=404,
            detail="Dataset desconocido; use detections, portfolio o watchlist",
        )
    build, title = builder
    if fmt not in ("csv", "md"):
        raise HTTPException(status_code=404, detail="Formato desconocido; use csv o md")

    headers, rows, name_es = build(conn, user)
    if fmt == "csv":
        return _csv_response(rows, headers, dataset)
    return _md_response(rows, headers, dataset, f"{title} — {name_es}")

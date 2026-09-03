"""Importación masiva y plantilla CSV del módulo portfolio.

Formato por defecto: CSV separado por ``;`` con BOM UTF-8 (compatible
con Excel en español). La plantilla descargable usa los rótulos canónicos
en español; la importación mapea por rótulo normalizado (tolera
mayúsculas, acentos, ``#`` y espacios).

Upsert: una marca que ya exista por ``#REGISTRO`` (registrada) o
``#SOLICITUD`` (por registrar) se actualiza; si no existe se crea con
estado por defecto ``Pendiente Resolución``.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional, TextIO

from scripts import db


# Rótulos canónicos de la plantilla (orden amigable para el usuario).
TEMPLATE_HEADERS = [
    "país", "marca", "estado", "etiqueta", "tipo registro", "bufete",
    "#solicitud", "f. solicitud", "#registro", "f. registro",
    "f. vencimiento", "clase", "productos/servicios", "titular",
    "tramitante", "empresa licenciada", "comentarios",
]

# Rótulo normalizado → columna de la tabla portfolio.
_HEADER_MAP = {
    "pais": "pais",
    "marca": "name",
    "estado": "status",
    "etiqueta": "etiqueta",
    "tiporegistro": "tipo_registro",
    "bufete": "bufete",
    "solicitud": "solicitud",
    "fsolicitud": "fecha_solicitud",
    "registro": "registro",
    "fregistro": "fecha_registro",
    "fvencimiento": "fecha_vencimiento",
    "clase": "class_nice",
    "productosservicios": "productos_servicios",
    "titular": "titular",
    "tramitante": "tramitante",
    "empresalicenciada": "empresa_licenciada",
    "comentarios": "comentarios",
}


def _normalize_header(label: str) -> str:
    """Normaliza un rótulo: minúsculas, sin acentos, sin ``#``/``.``/``/``."""
    s = label.lstrip("\ufeff").strip().lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[#./\s]+", "", s)


def _mapping_from_header(header: list[str]) -> dict[int, str]:
    """Posición → columna de la tabla usando rótulos normalizados."""
    mapping: dict[int, str] = {}
    for i, label in enumerate(header):
        field = _HEADER_MAP.get(_normalize_header(label))
        if field:
            mapping[i] = field
    return mapping


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"created": self.created, "updated": self.updated, "errors": self.errors}


def render_template() -> str:
    """Devuelve el CSV de plantilla (solo encabezados + una fila de ejemplo)."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(TEMPLATE_HEADERS)
    writer.writerow([
        "Venezuela", "EJEMPLO S.A.", "Pendiente Resolución", "", "Mixta",
        "", "2026-001234", "", "", "", "",
        "25", "CALZADO DEPORTIVO.", "", "", "", "",
    ])
    return "\ufeff" + buf.getvalue()


def _read_rows(fileobj: TextIO) -> tuple[list[dict[str, str]], list[str]]:
    reader = csv.reader(fileobj, delimiter=";")
    try:
        header = next(reader)
    except StopIteration:
        return [], ["El archivo está vacío (sin encabezados)."]
    mapping = _mapping_from_header(header)
    if not mapping:
        return [], ["El encabezado no coincide con la plantilla."]

    rows: list[dict[str, str]] = []
    errors: list[str] = []
    for lineno, raw in enumerate(reader, start=2):
        if not raw or all(not (c or "").strip() for c in raw):
            continue
        row: dict[str, str] = {}
        for i, col in mapping.items():
            value = (raw[i] if i < len(raw) else "").strip()
            if value:
                row[col] = value
        if not row.get("name"):
            errors.append(f"Fila {lineno}: falta el campo 'marca'.")
            continue
        rows.append(row)
    return rows, errors


def _as_int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_import(content: bytes | str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parsea el CSV y devuelve filas normalizadas + errores de formato."""
    text = content if isinstance(content, str) else content.decode("utf-8-sig", "replace")
    text = text.lstrip("\ufeff")
    rows, errors = _read_rows(io.StringIO(text))
    parsed: list[dict[str, Any]] = []
    for row in rows:
        clean = {
            k: (v if v else None)
            for k, v in row.items() if k != "name"
        }
        clean["name"] = row["name"]
        if clean.get("class_nice") is not None:
            clean["class_nice"] = _as_int(clean.pop("class_nice"))
            if clean["class_nice"] is None:
                errors.append(f"'{row['name']}': 'clase' no es un número.")
                continue
        parsed.append(clean)
    return parsed, errors


def apply_import(
    conn: sqlite3.Connection,
    user_id: int,
    rows: list[dict[str, Any]],
) -> ImportResult:
    """Upsert: actualiza por #REGISTRO/#SOLICITUD o crea la marca."""
    result = ImportResult()
    for row in rows:
        name = row.pop("name", "") or ""
        registro = row.get("registro")
        solicitud = row.get("solicitud")
        existing = db.portfolio_find_by_identity(
            conn, user_id, registro=registro, solicitud=solicitud,
        )
        if existing is not None:
            # Solo actualiza los campos que trae la fila (no vacía).
            updates = {k: v for k, v in row.items() if v not in (None, "")}
            updates.pop("class_nice", None)
            if row.get("class_nice") is not None:
                updates["class_nice"] = row["class_nice"]
            db.portfolio_update(conn, existing.id, user_id, **updates)
            result.updated += 1
            continue
        # Marca nueva: estado por defecto si no viene en el archivo.
        if not row.get("status"):
            row["status"] = "Pendiente Resolución"
        db.portfolio_add(
            conn,
            user_id=user_id,
            name=name,
            class_nice=row.get("class_nice"),
            pais=row.get("pais"),
            etiqueta=row.get("etiqueta"),
            tipo_registro=row.get("tipo_registro"),
            bufete=row.get("bufete"),
            solicitud=solicitud,
            fecha_solicitud=row.get("fecha_solicitud"),
            registro=registro,
            fecha_registro=row.get("fecha_registro"),
            fecha_vencimiento=row.get("fecha_vencimiento"),
            titular=row.get("titular"),
            tramitante=row.get("tramitante"),
            empresa_licenciada=row.get("empresa_licenciada"),
            productos_servicios=row.get("productos_servicios"),
            comentarios=row.get("comentarios"),
            status=row.get("status"),
        )
        result.created += 1
    return result
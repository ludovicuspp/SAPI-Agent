"""Alertas por lapsos legales derivadas de las disposiciones del boletín.

Fase 2 del gemelo digital: cada detección con un tipo de disposición
administrativa (o una publicación para oposición) abre un lapso que
corre desde la ``fecha_publicacion`` del boletín. El plazo se expresa
en **días hábiles** (lunes-viernes) y es **editable** desde la UI/API
(tabla ``lapse_config``); los valores por defecto son razonables y el
cliente puede confirmarlos (preguntas abiertas al Sr. Juan).

La fecha límite se recalcula al construir/refrescar la alerta; una vez
el usuario resuelve la alerta (``cumplida``/``descartada``) no se toca.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Optional

from scripts import db as _db


# ── Mapa tipo de disposición / estatus → lapso ──────────────────
# Conjunto cerrado de lapsos (ver CHECK en ``lapse_config``/``alerts``).
# ``REVOCA`` queda deliberadamente fuera: revocar una resolución no abre
# un lapso para la marca afectada.

LAPSO_POR_TIPO: dict[str, str] = {
    "CONCESION": "pago_concesion",
    "DEVOLUCION_FORMA": "subsanar_forma",
    "DEVOLUCION_FONDO": "subsanar_fondo",
    "NEGACION": "recurso_negacion",
    "CADUCA": "recurso_caducidad",
    "INADMISIBLE": "recurso_inadmisible",
}

# Un estatus PUBLIADA (orden de publicación) abre el lapso de oposición.
LAPSO_POR_ESTATUS: dict[str, str] = {
    "PUBLICADA": "oposicion",
}

# Plazos por defecto (días hábiles). El boletín real fija "treinta (30)
# días hábiles" para pagos y devoluciones; la oposición suele correr
# desde la publicación. Todos editables.
DEFAULT_LAPSOS: list[dict[str, Any]] = [
    {
        "key": "pago_concesion",
        "label": "Pago de tasa de registro (tras concesión)",
        "dias_habiles": 30,
    },
    {
        "key": "subsanar_forma",
        "label": "Subsanar devolución de forma",
        "dias_habiles": 30,
    },
    {
        "key": "subsanar_fondo",
        "label": "Subsanar devolución de fondo",
        "dias_habiles": 30,
    },
    {
        "key": "recurso_negacion",
        "label": "Recurso contra negación",
        "dias_habiles": 30,
    },
    {
        "key": "recurso_caducidad",
        "label": "Recurso contra caducidad",
        "dias_habiles": 30,
    },
    {
        "key": "recurso_inadmisible",
        "label": "Recurso (inadmisión del escrito)",
        "dias_habiles": 30,
    },
    {
        "key": "oposicion",
        "label": "Oposición a publicación",
        "dias_habiles": 30,
    },
]

DEFAULTS_BY_KEY: dict[str, dict[str, Any]] = {
    d["key"]: d for d in DEFAULT_LAPSOS
}


# ── Cálculo de días hábiles (lunes-viernes) ─────────────────────
# Nota: no se modelan feriados venezolanos; si el cliente los quiere
# considerar, se añadirían a una lista editable en ``lapse_config``.


def add_business_days(start: date, dias: int) -> date:
    """Suma ``dias`` hábiles (lun-vie) a ``start``. ``dias=0`` → mismo día."""
    d = start
    added = 0
    while added < dias:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def business_days_between(a: date, b: date) -> int:
    """Días hábiles en (a, b]: excluye ``a`` e incluye ``b``."""
    days = 0
    d = a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def _parse_iso(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# ── Resolución del lapso aplicable a una detección ──────────────


def lapse_key_for_detection(
    conn: sqlite3.Connection, detection: sqlite3.Row
) -> Optional[str]:
    """Devuelve el lapso aplicable a una detección (o ``None``).

    Prioridad: el tipo de disposición (efecto neto sobre la marca); si
    no hay disposición, el estatus PUBLIADA de su entrada (oposición).
    Los ``detections`` no guardan ``estatus``, así que se consulta la
    entrada por ``(boletin_id, expediente)``.
    """
    tipo = detection["tipo_disposicion"]
    if tipo in LAPSO_POR_TIPO:
        return LAPSO_POR_TIPO[tipo]
    if not detection["expediente"]:
        return None
    row = conn.execute(
        "SELECT estatus FROM boletin_entries"
        " WHERE boletin_id = ? AND expediente = ? LIMIT 1",
        (detection["boletin_id"], detection["expediente"]),
    ).fetchone()
    if row and row["estatus"] in LAPSO_POR_ESTATUS:
        return LAPSO_POR_ESTATUS[row["estatus"]]
    return None


# ── Reconstrucción de alertas para un boletín ───────────────────


def rebuild_alerts_for_boletin(
    conn: sqlite3.Connection,
    boletin_id: int,
    settings: Any = None,
) -> int:
    """(Re)calcula las alertas de lapso de todas las detecciones del boletín.

    Idempotente (``UNIQUE(user_id, detection_id)``): refresca la fecha
    límite de las pendientes y respeta las resueltas. Sin
    ``fecha_publicacion`` en el boletín no se genera ninguna alerta.
    """
    boletin = _db.boletines_get(conn, boletin_id)
    if boletin is None or not boletin.fecha_publicacion:
        return 0
    publicacion = _parse_iso(boletin.fecha_publicacion)
    if publicacion is None:
        return 0

    config = {c.key: c for c in _db.lapse_config_list(conn)}
    if not config:
        _db.lapse_config_seed(conn, DEFAULT_LAPSOS)
        config = {c.key: c for c in _db.lapse_config_list(conn)}

    rows = conn.execute(
        "SELECT * FROM detections WHERE boletin_id = ?", (boletin_id,)
    ).fetchall()

    created = 0
    for det in rows:
        clave = lapse_key_for_detection(conn, det)
        if not clave:
            continue
        cfg = config.get(clave)
        if cfg is None:
            continue
        limite = add_business_days(publicacion, cfg.dias_habiles)
        _db.alerts_upsert(
            conn,
            user_id=det["user_id"],
            detection_id=det["id"],
            boletin_id=boletin_id,
            lapse_key=clave,
            label=cfg.label,
            marca=det["mark_name"],
            expediente=det["expediente"],
            fecha_publicacion=boletin.fecha_publicacion,
            fecha_limite=limite.isoformat(),
            dias_habiles=cfg.dias_habiles,
        )
        created += 1
    return created


# ── Estado derivado y countdown ─────────────────────────────────


def derivar_estado(alerta: Any, hoy: Optional[date] = None) -> str:
    """Estado efectivo: ``vencida`` si está pendiente y pasó la fecha."""
    if alerta.estado != "pendiente":
        return alerta.estado
    limite = _parse_iso(alerta.fecha_limite)
    if limite is None:
        return alerta.estado
    hoy = hoy or datetime.now().date()
    return "vencida" if limite < hoy else "pendiente"


def dias_restantes(alerta: Any, hoy: Optional[date] = None) -> int:
    """Días calendario hasta la fecha límite (negativo = vencida)."""
    limite = _parse_iso(alerta.fecha_limite)
    if limite is None:
        return 0
    hoy = hoy or datetime.now().date()
    return (limite - hoy).days


# ── Recalcula las pendientes ante un cambio de configuración ────


def rebuild_pending_for_config(conn: sqlite3.Connection) -> int:
    """Reconstruye las alertas ``pendiente`` de todos los boletines con
    fecha (tras editar un plazo). Las resueltas se conservan."""
    rows = conn.execute(
        "SELECT id FROM boletines WHERE fecha_publicacion IS NOT NULL"
    ).fetchall()
    total = 0
    for r in rows:
        total += rebuild_alerts_for_boletin(conn, r["id"])
    return total
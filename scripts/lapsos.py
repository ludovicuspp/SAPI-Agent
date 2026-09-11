"""Alertas por lapsos legales derivadas de las disposiciones del boletín.

Los plazos se toman del propio boletín SAPI (cabecera de sección o
``disposicion`` de cada entrada) y, en su defecto, de los plazos
publicados en el texto íntegro de los artículos de la **Ley de
Propiedad Industrial** (LPI) que SAPI reimprime en cada edición
(arts. 77, 78, 83) y de la **Ley Orgánica de Procedimientos
Administrativos** (LOPA, art. 90) para los recursos.

  CONCESION          → pago de tasa, art. 83 LPI: 30 días (hábiles).
  DEVOLUCION_FORMA   → subsanar forma, art. 71 LPI: 30 días hábiles
                       desde la publicación (publicado en cabecera).
  DEVOLUCION_FONDO   → subsanar fondo, art. 72 LPI: 30 días hábiles
                       desde la publicación.
  NEGACION           → recurso de reconsideración, art. 90 LOPA: 15
                       días hábiles tras la notificación.
  INADMISIBLE        → recurso de reconsideración, art. 90 LOPA: 15
                       días hábiles.
  CADUCA             → comparecencia ante Taquilla, art. 86 LPI: 10
                       días hábiles (publicado en cabecera).
  PUBLICADA (estatus)→ oposición, art. 77 LPI: 30 días hábiles desde
                       la publicación.

``REVOCA`` queda deliberadamente fuera: revocar una resolución no
abre un lapso para la marca afectada.

Si una entrada concreta publica un plazo distinto en su ``disposicion``
o en la cabecera de la sección, ese valor (guardado como
``boletin_entries.lapse_dias_override`` por ``scripts/parsers/patterns/lapse.py``)
prevalece sobre el default legal.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Optional

from scripts import db as _db
from scripts.parsers.patterns.lapse import lapse_for_entry


# ── Mapa tipo de disposición / estatus → lapse_key ─────────────────
LAPSO_POR_TIPO: dict[str, str] = {
    "CONCESION": "pago_concesion",
    "DEVOLUCION_FORMA": "subsanar_forma",
    "DEVOLUCION_FONDO": "subsanar_fondo",
    "NEGACION": "recurso_negacion",
    "CADUCA": "recurso_caducidad",
    "INADMISIBLE": "recurso_inadmisible",
}

# Un estatus PUBLICADA (orden de publicación) abre el lapso de oposición.
LAPSO_POR_ESTATUS: dict[str, str] = {
    "PUBLICADA": "oposicion",
}

# Defaults legales (días hábiles). Fuente: arts. 77/78/83 LPI y art. 90
# LOPA tal como los reimprime el boletín SAPI. Editables en
# ``lapse_config`` desde la UI/API; un override explícito en la
# disposicion o cabecera del boletín prevalece sobre estos.
DEFAULT_LAPSOS: list[dict[str, Any]] = [
    {
        "key": "pago_concesion",
        "label": "Pago de tasa de registro (tras concesión, art. 83 LPI)",
        "dias_habiles": 30,
    },
    {
        "key": "subsanar_forma",
        "label": "Subsanar devolución de forma (art. 71 LPI)",
        "dias_habiles": 30,
    },
    {
        "key": "subsanar_fondo",
        "label": "Subsanar devolución de fondo (art. 72 LPI)",
        "dias_habiles": 30,
    },
    {
        "key": "recurso_negacion",
        "label": "Recurso contra negación (art. 90 LOPA)",
        "dias_habiles": 15,
    },
    {
        "key": "recurso_caducidad",
        "label": "Comparecencia por caducidad (art. 86 LPI)",
        "dias_habiles": 10,
    },
    {
        "key": "recurso_inadmisible",
        "label": "Recurso contra inadmisión (art. 90 LOPA)",
        "dias_habiles": 15,
    },
    {
        "key": "oposicion",
        "label": "Oposición a publicación (art. 77 LPI)",
        "dias_habiles": 30,
    },
]

DEFAULTS_BY_KEY: dict[str, dict[str, Any]] = {
    d["key"]: d for d in DEFAULT_LAPSOS
}


# ── Cálculo de días hábiles (lunes-viernes) ─────────────────────
# No se modelan feriados venezolanos; si el cliente los quiere
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


# ── Resolución del plazo concreto (override o default legal) ────


def lapse_dias_for_detection(
    conn: sqlite3.Connection, detection: sqlite3.Row, default: int
) -> tuple[int, str]:
    """Devuelve ``(dias, source)`` para una detección.

    Prioridad:
      1. ``boletin_entries.lapse_dias_override`` (leído del boletín).
      2. ``lapse_config.dias_habiles`` (configurable).
      3. ``default`` (default legal pasado).
    """
    if detection["expediente"]:
        row = conn.execute(
            "SELECT lapse_dias_override, lapse_dias_source"
            " FROM boletin_entries"
            " WHERE boletin_id = ? AND expediente = ? LIMIT 1",
            (detection["boletin_id"], detection["expediente"]),
        ).fetchone()
        if row and row["lapse_dias_override"]:
            return int(row["lapse_dias_override"]), (
                row["lapse_dias_source"] or "boletin_override"
            )
    return default, "lapse_config"


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
        default_dias = cfg.dias_habiles
        dias, source = lapse_dias_for_detection(conn, det, default_dias)
        limite = add_business_days(publicacion, dias)
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
            dias_habiles=dias,
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


# ── Helper: parseo directo desde disposicion + sección + fallback ─


def lapse_dias_for_entry(
    disposicion: Optional[str],
    section_header: Optional[str] = None,
    *,
    tipo: Optional[str] = None,
) -> tuple[Optional[int], str]:
    """Atajo para calcular el plazo de una ``boletin_entry`` concreta.

    Combina ``lapse_for_entry`` (regex sobre disposicion/cabecera) con
    el default legal del ``tipo`` si no hay match. Pensado para uso en
    el parser que rellena ``boletin_entries.lapse_dias_override``.
    """
    fallback = DEFAULTS_BY_KEY.get(LAPSO_POR_TIPO.get(tipo or "", ""), {}).get(
        "dias_habiles"
    )
    return lapse_for_entry(disposicion, section_header, fallback_lpi=fallback)
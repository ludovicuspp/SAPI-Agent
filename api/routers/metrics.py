"""GET /api/admin/metrics — métricas operacionales para el dashboard de admin.

Solo accesible por usuarios con rol ``admin``. Devuelve agregados de
``scans_log``, ``boletines``, ``detections`` y ``users`` con foco en:

- Volumen (boletines, detecciones, usuarios, watchlist, portfolio).
- Tasa de error por etapa del pipeline (extract, hermes, notify, match).
- Latencia (p50, p95, max en ms) por etapa, derivada de ``duration_ms``.
- Distribución de confidence y source en detecciones.
- Cola de Hermes (boletines pendientes de revisión visual).
- Estado del timer pull_deploy (si podemos leerlo vía /proc o journalctl).
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db, get_current_user
from scripts import db

router = APIRouter()


def _percentile(values: list[int], p: float) -> int:
    """Percentil simple (sin numpy). ``p`` ∈ [0, 1]."""
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[k]


@router.get("")
async def metrics(
    user: db.UserRow = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Métricas agregadas para el dashboard de monitoreo."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Solo admin")

    # ── Volumen ────────────────────────────────────────────────────
    counts = {
        "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "boletines_total": conn.execute("SELECT COUNT(*) FROM boletines").fetchone()[0],
        "boletines_por_status": {
            row["status"]: row["n"]
            for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM boletines GROUP BY status"
            ).fetchall()
        },
        "detections_total": conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0],
        "watchlist_total": conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0],
        "portfolio_total": conn.execute("SELECT COUNT(*) FROM portfolio").fetchone()[0],
    }

    # ── Cola de Hermes ─────────────────────────────────────────────
    counts["hermes_queue"] = conn.execute(
        "SELECT COUNT(*) FROM boletines WHERE needs_hermes_review=1 "
        "AND hermes_processed_at IS NULL"
    ).fetchone()[0]
    counts["hermes_processed_total"] = conn.execute(
        "SELECT COUNT(*) FROM boletines WHERE hermes_processed_at IS NOT NULL"
    ).fetchone()[0]

    # ── Tasa de error por etapa ───────────────────────────────────
    error_rates: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT kind, status, COUNT(*) AS n FROM scans_log GROUP BY kind, status"
    ).fetchall():
        kind = row["kind"]
        if kind not in error_rates:
            error_rates[kind] = {"ok": 0, "error": 0, "total": 0}
        error_rates[kind][row["status"]] = row["n"]
        error_rates[kind]["total"] += row["n"]
    for k, v in error_rates.items():
        v["error_rate_pct"] = round(
            100.0 * v["error"] / v["total"], 2
        ) if v["total"] else 0.0
    counts["error_rates"] = error_rates

    # ── Latencia por etapa (p50, p95, max) ─────────────────────────
    latency: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT kind, duration_ms FROM scans_log WHERE duration_ms IS NOT NULL"
    ).fetchall():
        kind = row["kind"]
        latency.setdefault(kind, {"values": []})["values"].append(int(row["duration_ms"]))
    latency_out: dict[str, dict] = {}
    for kind, data in latency.items():
        v = data["values"]
        latency_out[kind] = {
            "count": len(v),
            "p50_ms": _percentile(v, 0.50),
            "p95_ms": _percentile(v, 0.95),
            "max_ms": max(v) if v else 0,
        }
    counts["latency_ms"] = latency_out

    # ── Distribución de detecciones ────────────────────────────────
    counts["detections_by_source"] = {
        row["source"]: row["n"]
        for row in conn.execute(
            "SELECT source, COUNT(*) AS n FROM detections GROUP BY source"
        ).fetchall()
    }
    counts["detections_by_confidence"] = {
        row["confidence"]: row["n"]
        for row in conn.execute(
            "SELECT confidence, COUNT(*) AS n FROM detections GROUP BY confidence"
        ).fetchall()
    }
    counts["detections_by_match_kind"] = {
        row["match_kind"]: row["n"]
        for row in conn.execute(
            "SELECT match_kind, COUNT(*) AS n FROM detections GROUP BY match_kind"
        ).fetchall()
    }

    # ── Actividad reciente (últimas 24 h) ─────────────────────────
    counts["ultimas_24h"] = {
        "boletines": conn.execute(
            "SELECT COUNT(*) FROM boletines "
            "WHERE uploaded_at >= datetime('now', '-1 day')"
        ).fetchone()[0],
        "detections": conn.execute(
            "SELECT COUNT(*) FROM detections "
            "WHERE detected_at >= datetime('now', '-1 day')"
        ).fetchone()[0],
        "scans_ok": conn.execute(
            "SELECT COUNT(*) FROM scans_log "
            "WHERE created_at >= datetime('now', '-1 day') AND status='ok'"
        ).fetchone()[0],
        "scans_error": conn.execute(
            "SELECT COUNT(*) FROM scans_log "
            "WHERE created_at >= datetime('now', '-1 day') AND status='error'"
        ).fetchone()[0],
    }

    # ── Tasa de detección por boletín ─────────────────────────────
    rows = conn.execute(
        "SELECT boletin_id, COUNT(*) AS n FROM detections GROUP BY boletin_id"
    ).fetchall()
    if rows:
        counts["detections_por_boletin"] = {
            "min": min(r["n"] for r in rows),
            "max": max(r["n"] for r in rows),
            "avg": round(sum(r["n"] for r in rows) / len(rows), 2),
        }
    else:
        counts["detections_por_boletin"] = {"min": 0, "max": 0, "avg": 0}

    return counts
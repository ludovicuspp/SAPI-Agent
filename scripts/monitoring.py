"""Monitoreo y alertas de métricas fuera de rango (RNF-04 / RNF-27).

Funciones puras de cálculo de alertas y utilidad de envío; el endpoint
de métricas usa ``compute_metric_alerts`` para incluir alertas en la
respuesta. La CLI ``metrics-check`` las evalúa y envía email cuando
hay alertas de severidad alta (diseñada para ejecutarse vía cron/timer).
"""
from __future__ import annotations

import logging
from typing import Any

import sqlite3

from scripts.config import Settings

log = logging.getLogger(__name__)


def compute_metric_alerts(conn: sqlite3.Connection, cfg: Settings) -> list[dict[str, Any]]:
    """Devuelve lista de alertas cuyos valores superan los umbrales configurados."""
    alerts: list[dict[str, Any]] = []

    # RNF-04: tasa de falsos positivos entre detecciones con veredicto.
    row = conn.execute(
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN hermes_verdict='confirmed' THEN 1 ELSE 0 END) AS confirmed,"
        " SUM(CASE WHEN hermes_verdict='discarded' THEN 1 ELSE 0 END) AS discarded"
        " FROM detections WHERE hermes_verdict IS NOT NULL"
    ).fetchone()
    total_veredictos = (row["confirmed"] or 0) + (row["discarded"] or 0)
    if total_veredictos > 0:
        fp_pct = (row["discarded"] or 0) * 100.0 / total_veredictos
        if fp_pct > cfg.false_positive_threshold_pct:
            alerts.append(
                {
                    "metric": "false_positive_rate",
                    "value": round(fp_pct, 2),
                    "threshold": cfg.false_positive_threshold_pct,
                    "severity": "high",
                }
            )

    # RNF-27: profundidad de la cola de Hermes.
    row2 = conn.execute(
        "SELECT COUNT(*) AS n FROM boletines"
        " WHERE needs_hermes_review=1 AND hermes_processed_at IS NULL"
    ).fetchone()
    q = row2["n"] or 0
    if q > cfg.hermes_queue_threshold:
        alerts.append(
            {
                "metric": "hermes_queue_depth",
                "value": q,
                "threshold": cfg.hermes_queue_threshold,
                "severity": "medium",
            }
        )

    # RNF-27: tasa de errores por etapa en las últimas 24 h.
    rows = conn.execute(
        "SELECT kind,"
        " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors,"
        " COUNT(*) AS total"
        " FROM scans_log WHERE created_at >= datetime('now', '-1 day')"
        " GROUP BY kind HAVING errors > 0"
    ).fetchall()
    for r in rows:
        pct = r["errors"] * 100.0 / r["total"]
        if pct > cfg.error_rate_threshold_pct:
            alerts.append(
                {
                    "metric": f"error_rate_{r['kind']}",
                    "value": round(pct, 2),
                    "threshold": cfg.error_rate_threshold_pct,
                    "severity": "high",
                }
            )

    return alerts


def send_metric_alerts(
    alerts: list[dict[str, Any]],
    *,
    cfg: Settings | None = None,
) -> None:
    """Envía email si hay alertas de severidad alta (RNF-27).

    Degradación: si SMTP no está configurado, solo loguea.
    """
    high = [a for a in alerts if a.get("severity") == "high"]
    if not high:
        return
    if cfg is None:
        from scripts.config import get_settings
        cfg = get_settings()
    to = cfg.alert_emails_list
    if not to or not cfg.smtp_configured:
        log.warning("Alertas de métricas detectadas pero SMTP no configurado: %s", high)
        return
    from scripts.notifiers.email_smtp import send_event
    send_event(
        kind="fallo_sistema",
        to_addresses=to,
        context={
            "summary": f"{len(high)} alerta(s) de métricas fuera de rango",
            "alerts": str(high),
        },
    )

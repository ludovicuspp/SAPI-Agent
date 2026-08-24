"""Notificación por email vía SMTP (aiosmtplib).

Plantilla HTML en español con datos del boletín y de la detection.
Idempotente vía ``detection.notified_email``; el caller debe filtrar
las que aún no fueron notificadas.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Iterable

import aiosmtplib

from scripts.config import Settings, get_settings
from scripts.db import DetectionRow, BoletinRow


log = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    sent: int
    failed: list[int]


def _render_subject(detection: DetectionRow, boletin: BoletinRow | None) -> str:
    bn = f"#{boletin.bulletin_number}" if boletin and boletin.bulletin_number else ""
    return f"[SAPI-Agent] Coincidencia detectada {bn}: {detection.mark_name}"


def _render_html(detection: DetectionRow, boletin: BoletinRow | None) -> str:
    bn = boletin.bulletin_number if boletin else "—"
    periodo = boletin.period if boletin else "—"
    return f"""
<html><body style="font-family:Arial,sans-serif;color:#222">
  <h2 style="color:#c0392b">Coincidencia detectada en boletín SAPI</h2>
  <table style="border-collapse:collapse">
    <tr><td><b>Boletín</b></td><td>{bn} ({periodo})</td></tr>
    <tr><td><b>Marca detectada</b></td><td>{detection.mark_name}</td></tr>
    <tr><td><b>Expediente</b></td><td>{detection.expediente or '—'}</td></tr>
    <tr><td><b>Titular</b></td><td>{detection.titular or '—'}</td></tr>
    <tr><td><b>Clase Niza</b></td><td>{detection.class_nice or '—'}</td></tr>
    <tr><td><b>Similitud</b></td><td>{detection.similarity * 100:.1f}%</td></tr>
    <tr><td><b>Método</b></td><td>{detection.source}</td></tr>
    <tr><td><b>Confianza</b></td><td>{detection.confidence}</td></tr>
  </table>
  <p>Detectado: {detection.detected_at}</p>
  <hr/>
  <p style="color:#666;font-size:12px">
    SAPI-Agent · monitoreo automático de marcas registradas en SAPI Venezuela.
  </p>
</body></html>
""".strip()


def _build_message(
    *, from_addr: str, to_addr: str, subject: str, html: str
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(
        "Tu cliente de correo no soporta HTML. Abre esta alerta desde el dashboard."
    )
    msg.add_alternative(html, subtype="html")
    return msg


async def _send_one(
    msg: EmailMessage,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
) -> None:
    await aiosmtplib.send(
        msg,
        hostname=host,
        port=port,
        username=user,
        password=password,
        start_tls=True,
    )


def send_detection_emails(
    *,
    to_address: str,
    detections: Iterable[DetectionRow],
    boletines_by_id: dict[int, BoletinRow],
    settings: Settings | None = None,
) -> DeliveryResult:
    """Envía un email por cada detection. Bloquea hasta terminar.

    Retorna ``sent`` y ``failed`` con los ids que no se pudieron
    entregar. El caller debe hacer ``detections_mark_notified(sent)``
    solo sobre los exitosos.
    """
    cfg = settings or get_settings()
    if not cfg.smtp_configured:
        log.warning("SMTP no configurado; se omiten notificaciones por email.")
        return DeliveryResult(sent=0, failed=[])

    sent: list[int] = []
    failed: list[int] = []

    async def _run_all() -> None:
        for det in detections:
            boletin = boletines_by_id.get(det.boletin_id)
            subject = _render_subject(det, boletin)
            html = _render_html(det, boletin)
            msg = _build_message(
                from_addr=cfg.smtp_from, to_addr=to_address,
                subject=subject, html=html,
            )
            try:
                await _send_one(
                    msg,
                    host=cfg.smtp_host,
                    port=cfg.smtp_port,
                    user=cfg.smtp_user,
                    password=cfg.smtp_password,
                )
                sent.append(det.id)
            except (smtplib.SMTPException, ssl.SSLError, OSError) as e:
                log.error("Falló envío email detection %s: %s", det.id, e)
                failed.append(det.id)

    asyncio.run(_run_all())
    return DeliveryResult(sent=len(sent), failed=failed)


def render_digest(
    detections: list[DetectionRow],
    boletines_by_id: dict[int, BoletinRow],
    *,
    period_label: str | None = None,
) -> tuple[str, str]:
    """Genera un (subject, html) con el resumen de varias detections.

    Usado por ``send-digest`` del CLI.
    """
    if not period_label:
        period_label = datetime.utcnow().strftime("%Y-%m-%d")
    subject = f"[SAPI-Agent] Resumen {period_label}: {len(detections)} coincidencias"
    rows = []
    for d in detections:
        b = boletines_by_id.get(d.boletin_id)
        bn = f"#{b.bulletin_number}" if b and b.bulletin_number else "—"
        rows.append(
            f"<tr><td>{bn}</td><td>{d.mark_name}</td>"
            f"<td>{d.expediente or '—'}</td>"
            f"<td>{d.class_nice or '—'}</td>"
            f"<td>{d.similarity * 100:.1f}%</td>"
            f"<td>{d.source}</td></tr>"
        )
    html = f"""
<html><body style="font-family:Arial,sans-serif;color:#222">
  <h2>Resumen de coincidencias ({period_label})</h2>
  <p>Total: <b>{len(detections)}</b></p>
  <table border="1" cellpadding="4" style="border-collapse:collapse">
    <tr style="background:#eee">
      <th>Boletín</th><th>Marca</th><th>Expediente</th>
      <th>Clase</th><th>Similitud</th><th>Fuente</th>
    </tr>
    {"".join(rows)}
  </table>
</body></html>
""".strip()
    return subject, html

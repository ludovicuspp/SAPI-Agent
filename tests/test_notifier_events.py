"""Tests del notifier de eventos (send_event).

Cubre:
- send_event degrada a log silencioso si SMTP no está configurado
- send_event respeta los 5 tipos de eventos (boletin_nuevo, etc.)
- send_event envía a múltiples destinatarios si se pasan varios
- send_event maneja fallo SMTP sin romper
"""
from __future__ import annotations

import asyncio
import smtplib
from unittest.mock import patch

import pytest

from scripts.notifiers import email_smtp


# ── Helpers ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPI_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("JWT_SECRET", "test-secret-events")
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    from scripts.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── E.1: degrada silenciosamente si SMTP vacío ───────────────────


def test_send_event_degrada_sin_smtp():
    """Sin SMTP_USER/PASSWORD, send_event no rompe y devuelve sent=0."""
    result = email_smtp.send_event(
        kind="boletin_nuevo",
        to_addresses=["x@y.com"],
        context={"boletin_id": 1, "filename": "BPI-654.pdf"},
    )
    assert result.sent == 0
    assert result.failed == []


# ── E.2: 5 tipos de eventos soportados ────────────────────────────


@pytest.mark.parametrize("kind", [
    "boletin_nuevo",
    "extraccion_completada",
    "analisis_completado",
    "accion_estado",
    "fallo_sistema",
])
def test_send_event_cinco_tipos(kind):
    """Los 5 tipos de eventos no fallan con SMTP vacío."""
    result = email_smtp.send_event(
        kind=kind,
        to_addresses=["x@y.com"],
        context={"boletin_id": 1},
    )
    assert result.sent == 0
    assert result.failed == []


# ── E.3: múltiples destinatarios (lista) ─────────────────────────


def test_send_event_multiples_destinatarios_sin_smtp():
    result = email_smtp.send_event(
        kind="extraccion_completada",
        to_addresses=["a@x.com", "b@y.com", "c@z.com"],
        context={"boletin_id": 1, "filename": "BPI-654.pdf"},
    )
    assert result.sent == 0
    assert result.failed == []


# ── E.4: con SMTP configurado (mock) ─────────────────────────────


def test_send_event_envia_con_smtp(monkeypatch):
    """Con SMTP mockeado, send_event envía y registra sent=N."""
    monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "u@test.com")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    from scripts.config import get_settings
    get_settings.cache_clear()

    async def fake_send_one(msg, **kwargs):
        return None

    with patch.object(email_smtp, "_send_one", side_effect=fake_send_one):
        result = email_smtp.send_event(
            kind="analisis_completado",
            to_addresses=["a@x.com", "b@y.com"],
            context={"boletin_id": 42, "entries_matcheables": 5},
        )
    assert result.sent == 2
    assert result.failed == []


# ── E.5: fallo SMTP no rompe el caller ────────────────────────────


def test_send_event_fallo_smtp_no_rompe(monkeypatch):
    """Si aiosmtplib lanza SMTPException, send_event devuelve failed sin raise."""
    monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "u@test.com")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    from scripts.config import get_settings
    get_settings.cache_clear()

    async def fake_send_one(msg, **kwargs):
        raise smtplib.SMTPException("SMTP down")

    with patch.object(email_smtp, "_send_one", side_effect=fake_send_one):
        result = email_smtp.send_event(
            kind="fallo_sistema",
            to_addresses=["a@x.com"],
            context={"error": "x", "script": "pull_deploy.sh"},
        )
    assert result.sent == 0
    assert result.failed == [0]  # el índice 0 (a@x.com) falló


# ── E.6: subject se construye correctamente ──────────────────────


def test_render_event_subject():
    subj = email_smtp._render_event_subject(
        "boletin_nuevo",
        {"boletin_label": "BPI 654"},
    )
    assert "[SAPI-Agent]" in subj
    assert "Nuevo boletín" in subj
    assert "BPI 654" in subj


def test_render_event_subject_sin_suffix():
    subj = email_smtp._render_event_subject(
        "fallo_sistema",
        {},
    )
    # No debe terminar en ': '
    assert not subj.endswith(": ")
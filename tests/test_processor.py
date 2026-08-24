"""Tests end-to-end del processor y del notifier (con SMTP mockeado)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from scripts import db
from scripts.orchestration import processor


class TestProcessor:
    def test_process_sample_boletin(self, tmp_db, tmp_path):
        # Setup usuario y watchlist
        uid = db.users_create(tmp_db, "u@x.y", "h")
        db.watchlist_add(tmp_db, uid, "ACME")
        db.watchlist_add(tmp_db, uid, "MARTINEZ")

        fixture_pdf = Path("tests/fixtures/sample_boletin.pdf")
        if not fixture_pdf.exists():
            pytest.skip(f"No existe fixture: {fixture_pdf}")

        result = processor.process_pdf(
            fixture_pdf, user_id=uid, conn=tmp_db, notify=False
        )

        assert result.boletin_id > 0
        assert result.bulletin_number == 651
        assert "marzo" in (result.period or "").lower()
        assert result.pages_total >= 1
        assert result.entries_parsed >= 5
        assert result.detections_created >= 1

        # Verifica persistencia
        detections = db.detections_list_for_user(tmp_db, uid)
        assert len(detections) >= 1
        assert any("ACME" in d.mark_name for d in detections)

    def test_portfolio_status_updated(self, tmp_db, tmp_path):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        db.portfolio_add(
            tmp_db, uid, "MARCA PROPIA", expediente="2026-001234"
        )
        fixture_pdf = Path("tests/fixtures/sample_boletin.pdf")
        if not fixture_pdf.exists():
            pytest.skip(f"No existe fixture: {fixture_pdf}")

        processor.process_pdf(
            fixture_pdf, user_id=uid, conn=tmp_db, notify=False
        )

        portfolio = db.portfolio_list_for_user(tmp_db, uid)
        assert portfolio[0].status == "CONCEDIDA"

    def test_missing_file_raises(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        with pytest.raises(FileNotFoundError):
            processor.process_pdf(
                Path("/tmp/no-existe-xyz.pdf"),
                user_id=uid,
                conn=tmp_db,
                notify=False,
            )


class TestNotifierMocked:
    def test_send_when_smtp_configured(self, tmp_db, monkeypatch):
        # Configurar SMTP "real" para que el helper crea que está configurado
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_USER", "u@x.com")
        monkeypatch.setenv("SMTP_PASSWORD", "p")

        # Reimportar settings para que tome las nuevas vars
        from scripts.config import get_settings
        get_settings.cache_clear()

        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(
            tmp_db, uid, "f.pdf", "/tmp/f.pdf", "h"
        )
        db.detections_add(
            tmp_db,
            boletin_id=bid,
            user_id=uid,
            mark_name="ACME",
            similarity=0.9,
            match_kind="similar",
            source="pdfplumber_text",
            confidence="high",
        )

        # Mockear aiosmtplib.send
        from scripts.notifiers import email_smtp
        from scripts.db import detections_list_for_user

        with patch(
            "scripts.notifiers.email_smtp._send_one",
            new=AsyncMock(),
        ):
            pending = db.detections_pending_notification(tmp_db, uid)
            boletin = db.boletines_get(tmp_db, bid)
            delivery = email_smtp.send_detection_emails(
                to_address="u@x.y",
                detections=pending,
                boletines_by_id={bid: boletin},
            )

        assert delivery.sent == 1
        assert delivery.failed == []

    def test_skip_when_smtp_not_configured(self, tmp_db):
        # Asegurar SMTP vacío
        from scripts.config import get_settings
        get_settings.cache_clear()
        cfg = get_settings()
        # Garantizar vars vacías (incluso si hay .env)
        cfg.smtp_host = ""
        cfg.smtp_user = ""
        cfg.smtp_password = ""

        from scripts.notifiers import email_smtp

        # Detection dummy
        from scripts.db import DetectionRow
        det = DetectionRow(
            id=1, boletin_id=1, user_id=1, watchlist_id=None,
            portfolio_id=None, expediente="X", mark_name="X",
            titular=None, class_nice=None, page=None,
            similarity=0.9, match_kind="similar",
            source="pdfplumber_text", confidence="high",
            raw_excerpt=None, detected_at="2026-01-01",
            notified_email=0, notified_at=None,
        )
        delivery = email_smtp.send_detection_emails(
            to_address="u@x.y", detections=[det], boletines_by_id={}
        )
        assert delivery.sent == 0
        assert delivery.failed == []

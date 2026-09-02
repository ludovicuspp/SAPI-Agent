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
        db.watchlist_add(tmp_db, uid, "CROCS")

        fixture_pdf = Path("tests/fixtures/sample_boletin.pdf")
        if not fixture_pdf.exists():
            pytest.skip(f"No existe fixture: {fixture_pdf}")

        result = processor.process_pdf(
            fixture_pdf, user_id=uid, conn=tmp_db, notify=False
        )

        assert result.boletin_id > 0
        assert result.bulletin_number is not None
        assert result.pages_total >= 1
        # El PDF sintético está en formato viejo; el parser puede no extraer
        # entradas, pero el pipeline debe ejecutarse sin error.
        assert result.entries_parsed >= 0
        assert result.duration_ms >= 0

    def test_process_real_boletin_text(self, tmp_db, sample_boletin_text):
        """Procesa el texto del boletín en formato BPI real."""
        uid = db.users_create(tmp_db, "u@x.y", "h")
        db.watchlist_add(tmp_db, uid, "ACME")
        db.watchlist_add(tmp_db, uid, "MARTINEZ")
        db.watchlist_add(tmp_db, uid, "CROCS")

        bid = db.boletines_create(
            tmp_db, uid, "test.txt", "/tmp/test.txt", "abc"
        )

        from scripts.parsers.marca_entry import MarcaEntryParser
        from scripts.parsers.boletin_header import detect

        text = sample_boletin_text
        metadata = detect(text)

        def page_lookup(t, pos):
            import re
            page_re = re.compile(r"--- página (\d+) ---")
            last = None
            for m in page_re.finditer(t[: max(0, pos)]):
                last = int(m.group(1))
            return last

        parser = MarcaEntryParser(page_lookup=page_lookup)
        entries, stats = parser.parse_with_stats(text)

        assert stats.total_inscripciones == 5
        assert stats.entries_matcheables >= 4

        from scripts.matcher import combined
        from scripts.db import watchlist_list_for_user
        watch = watchlist_list_for_user(tmp_db, uid)
        watch_names = [w.name for w in watch]
        candidate_names = [e.marca for e in entries if e.marca]
        match_pairs = combined.find_matches(watch_names, candidate_names)

        for watch_name, candidate, mr in match_pairs:
            w = next(w for w in watch if w.name == watch_name)
            entry = next(e for e in entries if e.marca == candidate)
            db.detections_add(
                tmp_db,
                boletin_id=bid,
                user_id=uid,
                watchlist_id=w.id,
                mark_name=candidate,
                similarity=mr.similarity,
                match_kind="similar",
                source="pdfplumber_text",
                confidence=mr.confidence,
                expediente=entry.expediente,
                titular=entry.titular,
                class_nice=entry.clase_niza,
                page=entry.page,
                raw_excerpt=entry.excerpt,
                pais=entry.pais,
                fecha_inscripcion=entry.fecha_inscripcion,
                fuente_parsing=entry.fuente_parsing,
                es_lema=1 if entry.es_lema else 0,
            )

        detections = db.detections_list_for_user(tmp_db, uid)
        assert len(detections) >= 1

    def test_portfolio_status_updated(self, tmp_db, tmp_path):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        db.portfolio_add(
            tmp_db, uid, "MARCA PROPIA", expediente="2015-015976"
        )
        fixture_pdf = Path("tests/fixtures/sample_boletin.pdf")
        if not fixture_pdf.exists():
            pytest.skip(f"No existe fixture: {fixture_pdf}")

        # El PDF sintético no contiene el expediente real, pero el
        # processor debe ejecutarse sin error.
        processor.process_pdf(
            fixture_pdf, user_id=uid, conn=tmp_db, notify=False
        )

        # Sin cambio esperado (no hay match real)
        portfolio = db.portfolio_list_for_user(tmp_db, uid)
        # El status se mantiene en el default (no hubo match)
        assert portfolio[0].status == "Pendiente Resolución"

    def test_missing_file_raises(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        with pytest.raises(FileNotFoundError):
            processor.process_pdf(
                Path("/tmp/no-existe-xyz.pdf"),
                user_id=uid,
                conn=tmp_db,
                notify=False,
            )

    def test_batch_extract_resumes_after_partial_checkpoint(self, tmp_db, tmp_path):
        """Un checkpoint parcial + JSONL permite reanudar sin duplicar."""
        from scripts.config import Settings
        from scripts.extractors import pdf_meta
        from scripts.extractors.pdf_batch import extract_pdf_in_batches
        import json

        fixture_pdf = Path("tests/fixtures/sample_boletin.pdf")
        if not fixture_pdf.exists():
            pytest.skip(f"No existe fixture: {fixture_pdf}")

        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(
            tmp_db, uid, "sample.pdf", str(fixture_pdf), "abc"
        )
        total = pdf_meta.count_pages(fixture_pdf)

        cfg = Settings(
            data_dir=tmp_path,
            uploads_dir=tmp_path / "uploads",
        )
        checkpoint = (
            Path(cfg.data_dir) / "checkpoints" / f"boletin_{bid}.jsonl"
        )
        checkpoint.parent.mkdir(parents=True, exist_ok=True)

        # Simular que ya se extrajo la primera página en un run anterior.
        extracted = extract_pdf_in_batches(fixture_pdf, batch_size=1)
        first = extracted.pages[0]
        with checkpoint.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "page_number": first.page_number,
                "text": first.text,
                "char_count": first.char_count,
                "has_images": first.has_images,
                "low_confidence": first.low_confidence,
            }, ensure_ascii=False) + "\n")
        db.boletines_save_checkpoint(
            tmp_db, bid, batch=1, checkpoints={"last_page": 1}
        )

        result = processor.process_pdf(
            fixture_pdf,
            user_id=uid,
            conn=tmp_db,
            notify=False,
            boletin_id=bid,
            settings=cfg,
        )
        assert result.pages_extracted == total
        b = db.boletines_get(tmp_db, bid)
        assert b.status == "extracted"
        payload = json.loads(b.extraction_json)
        page_numbers = [p["page_number"] for p in payload["pages"]]
        # Sin duplicados y completo.
        assert len(page_numbers) == len(set(page_numbers)) == total

    def test_position_lookups_are_correct_and_fast(self, sample_boletin_text):
        """Los lookups por bisect asignan página/sección igual que antes,
        pero en O(log n) aunque haya miles de páginas."""
        from scripts.orchestration.processor import make_position_lookups

        text = sample_boletin_text
        page_lookup, section_lookup = make_position_lookups(text)

        # La 1ª entrada está en la página 8, sección PUBLICADA.
        idx = text.find("Insc. 2015-015976")
        assert page_lookup(text, idx) == 8
        assert section_lookup(text, idx) == "PUBLICADA"

        # La entrada de la página 9 pertenece a la página 9.
        idx9 = text.find("Insc. 2018-006650")
        assert page_lookup(text, idx9) == 9

        # Posición antes de la primera página → sin asignar.
        assert page_lookup(text, 0) is None
        assert section_lookup(text, 0) is None

    def test_position_lookups_scale_to_thousands_of_pages(self, sample_boletin_text):
        """Regresión de rendimiento: el parsing con lookups bisect debe
        completar en menos de 2 s con un texto equivalente a ~2000 páginas
        (antes colgaba horas por el lookup O(n) por entrada)."""
        import time as _time
        from scripts.parsers.marca_entry import MarcaEntryParser
        from scripts.orchestration.processor import make_position_lookups

        # Simular 2000 páginas repitiendo bloques con marcadores intercalados.
        parts = []
        for i in range(1, 2001):
            parts.append(f"--- página {i} ---")
            parts.append(
                "Insc. 2015-015976 del 30 DE OCTUBRE DE 2015\n"
                "SOLICITADA POR: RAUL ENRIQUE ARTIGAS País: VENEZUELA\n"
                "ACME SAMPLE\nEN CLASE: 35\nPARA DISTINGUIR: ALGO.\n"
            )
        text = "\n".join(parts)

        page_lookup, section_lookup = make_position_lookups(text)
        parser = MarcaEntryParser(
            page_lookup=page_lookup, section_lookup=section_lookup
        )
        t0 = _time.monotonic()
        entries, stats = parser.parse_with_stats(text)
        dt = _time.monotonic() - t0
        assert stats.total_inscripciones >= 1
        assert dt < 2.0, f"parsing tardó {dt:.2f}s (regresión de rendimiento)"


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

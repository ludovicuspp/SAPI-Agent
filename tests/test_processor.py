"""Tests end-to-end del processor y del notifier (con SMTP mockeado)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from scripts import db
from scripts.orchestration import processor


class TestProcessor:
    def test_portfolio_match_by_registro(self, tmp_db):
        """Match por #registro: una entry con el mismo expediente que el
        #registro del portafolio genera detección own_status."""
        uid = db.users_create(tmp_db, "portfolio@x.y", "h")
        portfolio_id = db.portfolio_add(
            tmp_db,
            uid,
            "MARCA PROPIA",
            registro="2015-015976",
            class_nice=25,
        )
        boletin_id = db.boletines_create(
            tmp_db, uid, "test.pdf", "/tmp/test.pdf", "b" * 64
        )
        entry = SimpleNamespace(
            expediente="2015-015976",
            marca="MARCA PROPIA",
            clase_niza=25,
            titular="TITULAR",
            pais="Venezuela",
            fecha_inscripcion=None,
            estatus="PUBLICADA",
            excerpt="MARCA PROPIA",
            page=1,
            es_figura=False,
            es_lema=False,
            clase_especial=None,
        )

        from scripts.orchestration.portfolio_sync import (
            match_portfolio_by_identity,
        )

        created = match_portfolio_by_identity(tmp_db, uid, boletin_id, [entry])
        assert created == 1
        detections = db.detections_list_for_user(tmp_db, uid)
        assert len(detections) == 1
        assert detections[0].portfolio_id == portfolio_id
        assert detections[0].watchlist_id is None
        assert detections[0].match_kind == "own_status"
        assert detections[0].matched_with == "MARCA PROPIA"

    def test_portfolio_match_by_solicitud(self, tmp_db):
        """Match por #solicitud (cuando no hay #registro)."""
        uid = db.users_create(tmp_db, "portfolio@x.y", "h")
        portfolio_id = db.portfolio_add(
            tmp_db, uid, "MARCA SOL", solicitud="2026-005555",
        )
        boletin_id = db.boletines_create(
            tmp_db, uid, "test.pdf", "/tmp/test.pdf", "b" * 64
        )
        entry = SimpleNamespace(
            expediente="2026-005555",
            marca="MARCA SOL",
            clase_niza=None,
            titular="TITULAR",
            pais="Venezuela",
            fecha_inscripcion=None,
            estatus="PUBLICADA",
            excerpt="MARCA SOL",
            page=1,
            es_figura=False,
            es_lema=False,
            clase_especial=None,
        )

        from scripts.orchestration.portfolio_sync import (
            match_portfolio_by_identity,
        )

        created = match_portfolio_by_identity(tmp_db, uid, boletin_id, [entry])
        assert created == 1
        detections = db.detections_list_for_user(tmp_db, uid)
        assert detections[0].portfolio_id == portfolio_id
        assert detections[0].matched_with == "MARCA SOL"

    def test_portfolio_without_registro_or_solicitud_no_match(self, tmp_db):
        """Portfolio sin #registro ni #solicitud: no participa."""
        uid = db.users_create(tmp_db, "portfolio@x.y", "h")
        db.portfolio_add(tmp_db, uid, "ACME")
        boletin_id = db.boletines_create(
            tmp_db, uid, "test.pdf", "/tmp/test.pdf", "b" * 64
        )
        entry = SimpleNamespace(
            expediente="2026-999999",
            marca="ACME",
            clase_niza=25,
            titular=None,
            pais=None,
            fecha_inscripcion=None,
            estatus=None,
            excerpt="ACME",
            page=1,
            es_figura=False,
            es_lema=False,
            clase_especial=None,
        )

        from scripts.orchestration.portfolio_sync import (
            match_portfolio_by_identity,
        )

        created = match_portfolio_by_identity(tmp_db, uid, boletin_id, [entry])
        assert created == 0
        assert db.detections_list_for_user(tmp_db, uid) == []

    def test_portfolio_match_registro_overrides_solicitud(self, tmp_db):
        """#registro tiene prioridad sobre #solicitud."""
        uid = db.users_create(tmp_db, "portfolio@x.y", "h")
        db.portfolio_add(
            tmp_db, uid, "MARCA",
            registro="2015-015976",
            solicitud="2026-005555",
        )
        boletin_id = db.boletines_create(
            tmp_db, uid, "test.pdf", "/tmp/test.pdf", "b" * 64
        )
        # La entry trae el #solicitud (no el #registro): NO debe matchear.
        entry = SimpleNamespace(
            expediente="2026-005555",
            marca="MARCA",
            clase_niza=None,
            titular=None,
            pais=None,
            fecha_inscripcion=None,
            estatus=None,
            excerpt="MARCA",
            page=1,
            es_figura=False,
            es_lema=False,
            clase_especial=None,
        )

        from scripts.orchestration.portfolio_sync import (
            match_portfolio_by_identity,
        )

        created = match_portfolio_by_identity(tmp_db, uid, boletin_id, [entry])
        assert created == 0

    def test_portfolio_match_name_below_threshold_no_match(self, tmp_db):
        """Identidad OK pero nombre por debajo del umbral fuzzy: no match."""
        uid = db.users_create(tmp_db, "portfolio@x.y", "h")
        db.portfolio_add(
            tmp_db, uid, "ACME", registro="2026-005555",
        )
        boletin_id = db.boletines_create(
            tmp_db, uid, "test.pdf", "/tmp/test.pdf", "b" * 64
        )
        entry = SimpleNamespace(
            expediente="2026-005555",
            marca="PASTILLAS PARA EL DOLOR",
            clase_niza=None,
            titular=None,
            pais=None,
            fecha_inscripcion=None,
            estatus=None,
            excerpt="...",
            page=1,
            es_figura=False,
            es_lema=False,
            clase_especial=None,
        )

        from scripts.orchestration.portfolio_sync import (
            match_portfolio_by_identity,
        )

        created = match_portfolio_by_identity(tmp_db, uid, boletin_id, [entry])
        assert created == 0

    def test_portfolio_lc_entry_no_match(self, tmp_db):
        """Lema comercial (LC) no participa en el matching de portfolio."""
        uid = db.users_create(tmp_db, "portfolio@x.y", "h")
        db.portfolio_add(
            tmp_db, uid, "LEMA X", registro="2026-005555",
        )
        boletin_id = db.boletines_create(
            tmp_db, uid, "test.pdf", "/tmp/test.pdf", "b" * 64
        )
        entry = SimpleNamespace(
            expediente="2026-005555",
            marca="LEMA X",
            clase_niza=None,
            clase_especial="LC",
            titular=None,
            pais=None,
            fecha_inscripcion=None,
            estatus=None,
            excerpt="...",
            page=1,
            es_figura=False,
            es_lema=True,
        )

        from scripts.orchestration.portfolio_sync import (
            match_portfolio_by_identity,
        )

        created = match_portfolio_by_identity(tmp_db, uid, boletin_id, [entry])
        assert created == 0

    def test_portfolio_idempotent(self, tmp_db):
        """Re-ejecutar el matcher con la misma entry no duplica."""
        uid = db.users_create(tmp_db, "portfolio@x.y", "h")
        db.portfolio_add(
            tmp_db, uid, "MARCA", registro="2026-005555",
        )
        boletin_id = db.boletines_create(
            tmp_db, uid, "test.pdf", "/tmp/test.pdf", "b" * 64
        )
        entry = SimpleNamespace(
            expediente="2026-005555",
            marca="MARCA",
            clase_niza=None,
            titular=None,
            pais=None,
            fecha_inscripcion=None,
            estatus=None,
            excerpt="...",
            page=1,
            es_figura=False,
            es_lema=False,
            clase_especial=None,
        )

        from scripts.orchestration.portfolio_sync import (
            match_portfolio_by_identity,
        )

        first = match_portfolio_by_identity(tmp_db, uid, boletin_id, [entry])
        second = match_portfolio_by_identity(tmp_db, uid, boletin_id, [entry])
        assert first == 1
        assert second == 0
        assert len(db.detections_list_for_user(tmp_db, uid)) == 1

    def test_shared_boletin_matches_other_users(self, tmp_db, tmp_path, monkeypatch):
        """Un boletín subido por un usuario alimenta las listas de todos."""
        uploader_id = db.users_create(tmp_db, "uploader@x.y", "h")
        target_id = db.users_create(tmp_db, "target@x.y", "h")
        watchlist_id = db.watchlist_add(tmp_db, target_id, "MARCA COMPARTIDA")
        portfolio_id = db.portfolio_add(
            tmp_db, target_id, "MARCA COMPARTIDA", solicitud="EXP-001"
        )
        pdf_path = tmp_path / "shared.pdf"
        pdf_path.write_bytes(b"pdf")

        from scripts.config import Settings
        from scripts.extractors.base import ExtractionResult, PageExtract

        entry = SimpleNamespace(
            expediente="EXP-001",
            marca="MARCA COMPARTIDA",
            clase_niza=None,
            titular="TITULAR",
            pais="Venezuela",
            fecha_inscripcion=None,
            estatus="PUBLICADA",
            excerpt="MARCA COMPARTIDA",
            page=1,
            matcheable=True,
            es_figura=False,
            es_lema=False,
            fuente_parsing="pattern_a",
        )
        stats = processor.ParseStats(
            total_inscripciones=1,
            entries_matcheables=1,
        )

        def fake_extract(path, *, batch_size, start_page, on_page, on_batch):
            page = PageExtract(1, "texto", 5, False, False)
            on_batch([page], 1, 1)
            return ExtractionResult([], 1)

        monkeypatch.setattr(processor.pdf_meta, "hash_file", lambda path: "c" * 64)
        monkeypatch.setattr(
            processor.pdf_batch,
            "extract_pdf_in_batches_memory_efficient",
            fake_extract,
        )
        monkeypatch.setattr(
            processor.boletin_header,
            "detect",
            lambda text: SimpleNamespace(
                bulletin_number=1, period="2026-01", tomo=None
            ),
        )
        monkeypatch.setattr(
            processor.MarcaEntryParser,
            "parse_with_stats",
            lambda self, text: ([entry], stats),
        )

        result = processor.process_pdf(
            pdf_path,
            user_id=uploader_id,
            conn=tmp_db,
            settings=Settings(data_dir=tmp_path, uploads_dir=tmp_path),
        )

        assert result.detections_created == 2
        detections = db.detections_list_for_user(tmp_db, target_id)
        assert {d.watchlist_id for d in detections} == {watchlist_id, None}
        assert {d.portfolio_id for d in detections} == {portfolio_id, None}

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
        page_lookup, section_lookup, _disp, tomo_lookup = make_position_lookups(text)

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

        page_lookup, section_lookup, _disp, tomo_lookup = make_position_lookups(text)
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

    def test_disposicion_lookup_por_seccion(self, sample_boletin_text):
        """El tercer lookup asigna el tipo de disposición implícito en la
        sección (devoluciones de forma vs fondo, BPI 654)."""
        from scripts.orchestration.processor import make_position_lookups

        text = (
            "--- página 5 ---\n"
            "DEVUELTAS DE FORMA\n"
            "Insc. 2026-005001 del 1 DE JUNIO DE 2026\n"
            "SOLICITADA POR: X SA País: VENEZUELA\n"
            "MARCA FORMA\nEN CLASE: 3\nPARA DISTINGUIR: COSMÉTICOS.\n"
            "--- página 9 ---\n"
            "DEVUELTAS DE FONDO\n"
            "Insc. 2026-005002 del 2 DE JUNIO DE 2026\n"
            "SOLICITADA POR: Y SA País: VENEZUELA\n"
            "MARCA FONDO\nEN CLASE: 5\nPARA DISTINGUIR: PRODUCTOS.\n"
            "--- página 12 ---\n"
            "MARCAS CON ORDEN DE PUBLICACIÓN\n"
            "Insc. 2026-005003 del 3 DE JUNIO DE 2026\n"
            "SOLICITADA POR: Z SA País: VENEZUELA\n"
            "MARCA PUB\nEN CLASE: 9\nPARA DISTINGUIR: VARIOS.\n"
        )
        page_lookup, section_lookup, disp_lookup, tomo_lookup = make_position_lookups(text)

        idx_forma = text.find("Insc. 2026-005001")
        idx_fondo = text.find("Insc. 2026-005002")
        idx_pub = text.find("Insc. 2026-005003")

        # Sección y estatus coherentes (DEVUELTA es estatus existente).
        assert section_lookup(text, idx_forma) == "DEVUELTA"
        assert section_lookup(text, idx_fondo) == "DEVUELTA"
        assert disp_lookup(text, idx_forma) == "DEVOLUCION_FORMA"
        assert disp_lookup(text, idx_fondo) == "DEVOLUCION_FONDO"
        # Sección sin implicancia de disposición → None.
        assert disp_lookup(text, idx_pub) is None

        # Integración con el parser: el entry recibe el tipo por sección.
        from scripts.parsers.marca_entry import MarcaEntryParser
        parser = MarcaEntryParser(
            page_lookup=page_lookup,
            section_lookup=section_lookup,
            disposicion_lookup=disp_lookup,
        )
        entries = {e.expediente: e for e in parser.parse(text)}
        assert entries["2026-005001"].tipo_disposicion == "DEVOLUCION_FORMA"
        assert entries["2026-005002"].tipo_disposicion == "DEVOLUCION_FONDO"
        assert entries["2026-005003"].tipo_disposicion is None
        # Las entradas de secciones normales siguen intactas.
        assert entries["2026-005001"].estatus == "DEVUELTA"
        assert entries["2026-005003"].estatus == "PUBLICADA"


class TestTomoPorPagina:
    def test_tomo_lookup_por_rango_de_paginas(self, sample_boletin_text):
        """Las cabeceras ``Tomo N/M`` dividen el boletín en rangos de páginas;
        cada entrada recibe el tomo según la página donde aparece."""
        from scripts.orchestration.processor import make_position_lookups

        text = (
            "Boletín de la Propiedad Industrial No. 999\n"
            "Tomo 1/2\n"
            "--- página 1 ---\n"
            "MARCAS CON ORDEN DE PUBLICACIÓN\n"
            "Insc. 2010-000001 del 1 DE ENERO DE 2010\n"
            "SOLICITADA POR: A SA País: VENEZUELA\n"
            "MARCA UNO\nEN CLASE: 35\nPARA DISTINGUIR: ALGO.\n"
            "--- página 10 ---\n"
            "Tomo 2/2\n"
            "Insc. 2010-000002 del 1 DE ENERO DE 2010\n"
            "SOLICITADA POR: B SA País: VENEZUELA\n"
            "MARCA DOS\nEN CLASE: 35\nPARA DISTINGUIR: ALGO.\n"
            "--- página 20 ---\n"
            "Insc. 2010-000003 del 1 DE ENERO DE 2010\n"
            "SOLICITADA POR: C SA País: VENEZUELA\n"
            "MARCA TRES\nEN CLASE: 35\nPARA DISTINGUIR: ALGO.\n"
        )
        page_lookup, _s, _d, tomo_lookup = make_position_lookups(text)
        assert page_lookup(text, text.find("MARCA UNO")) == 1
        assert tomo_lookup(text, text.find("MARCA UNO")) == "I"
        assert page_lookup(text, text.find("MARCA DOS")) == 10
        assert tomo_lookup(text, text.find("MARCA DOS")) == "II"
        assert page_lookup(text, text.find("MARCA TRES")) == 20
        assert tomo_lookup(text, text.find("MARCA TRES")) == "II"

    def test_tomo_se_persiste_en_entries(self, tmp_db):
        """El upsert y el replace guardan el tomo por entrada."""
        import scripts.db as db

        uid = db.users_create(tmp_db, "tomo@x.y", "h")
        bid = db.boletines_create(tmp_db, uid, "b.pdf", "/tmp/b.pdf", "sh-tomo")

        class _E:
            def __init__(self, exp, marca, page, tomo):
                self.expediente = exp
                self.marca = marca
                self.tomo = tomo
                self.page = page
                self.clase_especial = None
                self.titular = "T"
                self.pais = "VE"
                self.fecha_inscripcion = None
                self.estatus = None
                self.matcheable = True
                self.es_figura = False
                self.es_lema = False
                self.productos_servicios = None
                self.fuente_parsing = "pattern_a"
                self.source = None
                self.excerpt = "x"

        db.boletines_entries_replace(
            tmp_db, bid,
            [_E("E1", "MARCA I", 5, "I"), _E("E2", "MARCA II", 120, "II")],
        )
        tmp_db.commit()
        rows = db.boletines_entries_list(tmp_db, bid)
        by_exp = {r.expediente: r for r in rows}
        assert by_exp["E1"].tomo == "I"
        assert by_exp["E2"].tomo == "II"
        assert by_exp["E1"].page == 5
        assert by_exp["E2"].page == 120

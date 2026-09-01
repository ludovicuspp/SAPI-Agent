"""Tests del extractor por lotes y del checkpoint de extracción."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import db
from scripts.extractors import pdf_batch
from scripts.extractors.pdf_batch import (
    extract_pdf_in_batches,
    extract_pdf_in_batches_memory_efficient,
)


@pytest.fixture()
def sample_pdf_path() -> Path:
    p = Path("tests/fixtures/sample_boletin.pdf")
    if not p.exists():
        pytest.skip(f"No existe fixture: {p}")
    return p


class TestBatchExtractor:
    def test_total_pages_matches_meta(self, sample_pdf_path):
        from scripts.extractors import pdf_meta

        expected = pdf_meta.count_pages(sample_pdf_path)
        result = extract_pdf_in_batches(sample_pdf_path, batch_size=1)
        assert result.total_pages == expected
        assert len(result.pages) == expected

    def test_on_batch_receives_all_pages(self, sample_pdf_path):
        received: list[int] = []

        def on_batch(pages, start, end):
            for p in pages:
                received.append(p.page_number)

        result = extract_pdf_in_batches(
            sample_pdf_path, batch_size=5, on_batch=on_batch
        )
        assert received == list(range(1, result.total_pages + 1))

    def test_on_page_callback_counts(self, sample_pdf_path):
        calls: list[int] = []

        def on_page(page_no, total):
            calls.append(page_no)

        result = extract_pdf_in_batches(
            sample_pdf_path, batch_size=2, on_page=on_page
        )
        assert calls == list(range(1, result.total_pages + 1))

    def test_memory_efficient_does_not_retain_pages(self, sample_pdf_path):
        batch_counts: list[int] = []

        def on_batch(pages, start, end):
            batch_counts.append(len(pages))

        result = extract_pdf_in_batches_memory_efficient(
            sample_pdf_path, batch_size=3, on_batch=on_batch
        )
        assert result.pages == []
        assert result.total_pages >= 1
        assert sum(batch_counts) == result.total_pages

    def test_start_page_skips_earlier_pages(self, sample_pdf_path):
        received: list[int] = []

        def on_batch(pages, start, end):
            for p in pages:
                received.append(p.page_number)

        total = extract_pdf_in_batches(sample_pdf_path, batch_size=1000).total_pages
        result = extract_pdf_in_batches(
            sample_pdf_path,
            batch_size=1,
            start_page=2,
            on_batch=on_batch,
        )
        assert result.total_pages == total
        # start_page=2 no salta páginas del total, solo deja de leer antes,
        # pero el total reportado es el del documento.
        assert all(n >= 2 for n in received)


class TestCheckpointDB:
    def test_save_and_get_checkpoint(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(tmp_db, uid, "f.pdf", "/tmp/f.pdf", "abc")

        db.boletines_save_checkpoint(
            tmp_db, bid, batch=100, checkpoints={"last_page": 100}
        )
        batch, ck = db.boletines_get_checkpoint(tmp_db, bid)
        assert batch == 100
        assert ck["last_page"] == 100

    def test_get_checkpoint_empty(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(tmp_db, uid, "f.pdf", "/tmp/f.pdf", "abc")
        batch, ck = db.boletines_get_checkpoint(tmp_db, bid)
        assert batch is None
        assert ck == {}

    def test_mark_extracted_clears_checkpoint(self, tmp_db):
        uid = db.users_create(tmp_db, "u@x.y", "h")
        bid = db.boletines_create(tmp_db, uid, "f.pdf", "/tmp/f.pdf", "abc")
        db.boletines_save_checkpoint(
            tmp_db, bid, batch=50, checkpoints={"last_page": 50}
        )
        db.boletines_mark_extracted(
            tmp_db,
            boletin_id=bid,
            pages=50,
            extraction_payload={"pages": []},
            bulletin_number=None,
            period=None,
            needs_hermes_review=False,
        )
        batch, ck = db.boletines_get_checkpoint(tmp_db, bid)
        assert batch is None
        assert ck == {}

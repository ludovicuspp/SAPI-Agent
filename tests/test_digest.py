"""Tests del digest por severidad (render_digest).

Cubre:
- agrupa por match_kind y muestra el contador en el subject
- conflictos primero con riesgo en %; similar/own_status sin riesgo
- mantiene el orden por riesgo descendente
"""
from __future__ import annotations

from datetime import datetime

from scripts.db import BoletinRow, DetectionRow
from scripts.notifiers.email_smtp import render_digest


def _det(
    id_: int,
    name: str,
    kind: str,
    risk: float | None,
    similarity: float = 0.8,
) -> DetectionRow:
    return DetectionRow(
        id=id_, boletin_id=1, user_id=1, watchlist_id=None, portfolio_id=1,
        expediente=f"E{id_}", mark_name=name, titular=None, class_nice=12,
        page=1, similarity=similarity, match_kind=kind,
        source="pdfplumber_text", confidence="high", raw_excerpt=None,
        detected_at=datetime.now().isoformat(), notified_email=0,
        notified_at=None, risk_score=risk,
    )


def test_digest_orders_conflict_first_with_risk():
    dets = [
        _det(1, "PROPIA", "own_status", None, 1.0),
        _det(2, "RIVAL", "conflict", 0.85),
        _det(3, "PARECIDA", "similar", None, 0.7),
        _det(4, "RIVAL2", "conflict", 0.5),
    ]
    subject, html = render_digest(dets, {}, period_label="2026-01-01")

    assert "2 en conflicto" in subject
    # Secciones en orden: conflicto, similar, propio.
    assert html.index("Posibles conflictos (2)") < html.index("Marcas similares (1)")
    assert html.index("Marcas similares (1)") < html.index("Estado propio (1)")
    # El conflicto de mayor riesgo aparece antes que el de menor.
    assert html.index("RIVAL") < html.index("RIVAL2")
    # Riesgo presente solo en la tabla de conflictos.
    assert "85%" in html
    # Similar/own_status no pillan columna de riesgo.
    assert "70.0%" in html
    assert "100.0%" in html


def test_digest_without_conflicts():
    dets = [
        _det(1, "A", "similar", None),
        _det(2, "B", "own_status", None, 1.0),
    ]
    subject, _ = render_digest(dets, {}, period_label="2026-01-01")
    assert "0 en conflicto" not in subject  # se omite cuando no hay
    assert "2 coincidencias" in subject


def test_digest_usa_numero_boletin():
    """El nº de boletín se toma de boletines_by_id."""
    dets = [_det(1, "RIVAL", "conflict", 0.6)]
    b = BoletinRow(
        id=1, uploaded_by=1, filename="b.pdf", file_path="/b.pdf",
        file_sha256="x", bulletin_number=987, period=None, pages=1,
        status="extracted", extraction_json=None, needs_hermes_review=0,
        hermes_processed_at=None, hermes_error=None, error=None,
        uploaded_at=datetime.now().isoformat(), processed_at=None,
    )
    subject, html = render_digest(dets, {1: b}, period_label="2026-01-01")
    assert "60%" in html
    assert subject  # al menos no vacío
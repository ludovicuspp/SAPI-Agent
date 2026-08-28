"""Tests del endpoint /api/admin/metrics (dashboard de monitoreo)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.deps import get_db
from scripts import auth, db


@pytest.fixture(autouse=True)
def _settings(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "test_metrics.db"
    db.init_db(db_file)
    monkeypatch.setenv("SAPI_DB_PATH", str(db_file))
    monkeypatch.setenv("JWT_SECRET", "test-secret-metrics")
    monkeypatch.setenv("JWT_EXPIRES_MIN", "60")
    from scripts.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client(tmp_path: Path):
    db_file = tmp_path / "test_metrics.db"
    app = create_app()
    conn = db.connect(db_file)
    admin_id = db.users_create(conn, "admin@test.local", auth.hash_password("admin1234"), role="admin")
    agent_id = db.users_create(conn, "agent@test.local", auth.hash_password("agent1234"), role="agent")
    # Sembrar datos: 2 boletines, 1 watchlist, 1 detection, 3 scans_log
    sha = "a" * 64
    b1 = db.boletines_create(conn, admin_id, "B1.pdf", "/tmp/B1.pdf", sha)
    b2 = db.boletines_create(conn, agent_id, "B2.pdf", "/tmp/B2.pdf", sha + "b")
    db.boletines_mark_extracted(
        conn, boletin_id=b1, pages=10,
        extraction_payload={"pages": []}, bulletin_number=654, period="2026-02",
        needs_hermes_review=True, entries_matcheables=5,
    )
    db.boletines_mark_extracted(
        conn, boletin_id=b2, pages=20,
        extraction_payload={"pages": []}, bulletin_number=655, period="2026-02",
        needs_hermes_review=False, entries_matcheables=3,
    )
    db.watchlist_add(conn, admin_id, "ACME", class_nice=25, notes=None)
    db.detections_add(
        conn, boletin_id=b1, user_id=admin_id, mark_name="ACME",
        similarity=0.95, match_kind="similar",
        source="pdfplumber_text", confidence="high",
    )
    db.scans_log_record(conn, kind="extract", boletin_id=b1, status="ok", duration_ms=1200)
    db.scans_log_record(conn, kind="extract", boletin_id=b2, status="ok", duration_ms=3000)
    db.scans_log_record(conn, kind="hermes", boletin_id=b1, status="ok", duration_ms=8500)
    conn.commit()
    conn.close()

    def _override_get_db():
        c = db.connect(db_file)
        try:
            yield c
        finally:
            c.close()
    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app), db_file, admin_id, agent_id


def _token_for(db_file: Path, user_id: int, role: str) -> str:
    from scripts.auth import create_access_token
    from scripts.config import get_settings
    return create_access_token(
        user_id, role,
        secret=get_settings().jwt_secret,
        expires_min=60,
    )


# ── M.1: acceso solo admin ────────────────────────────────────────


def test_metrics_endpoint_requires_admin(client):
    c, db_file, _admin_id, agent_id = client
    token = _token_for(db_file, agent_id, "agent")
    r = c.get("/api/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_metrics_endpoint_admin_ok(client):
    c, db_file, admin_id, _agent_id = client
    token = _token_for(db_file, admin_id, "admin")
    r = c.get("/api/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["users"] == 2
    assert body["users_active"] == 2
    assert body["boletines_total"] == 2
    assert "extracted" in body["boletines_por_status"]
    assert body["detections_total"] == 1
    assert body["watchlist_total"] == 1


def test_metrics_endpoint_sin_auth_401(client):
    c, *_ = client
    r = c.get("/api/admin/metrics")
    assert r.status_code == 401


# ── M.2: error_rates ──────────────────────────────────────────────


def test_metrics_error_rates_calcula_pct(client):
    c, db_file, admin_id, _ = client
    token = _token_for(db_file, admin_id, "admin")
    r = c.get("/api/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    body = r.json()
    er = body["error_rates"]
    assert "extract" in er
    assert er["extract"]["ok"] == 2
    assert er["extract"]["error"] == 0
    assert er["extract"]["error_rate_pct"] == 0.0


def test_metrics_error_rates_con_error(client, tmp_path: Path):
    """Si hay scans con status='error', se calcula correctamente."""
    db_file = tmp_path / "test_metrics2.db"
    conn = db.connect(db_file)
    db.init_db(db_file)
    admin_id = db.users_create(conn, "admin@t.local", auth.hash_password("a1234567"), role="admin")
    sha = "c" * 64
    b = db.boletines_create(conn, admin_id, "B.pdf", "/tmp/B.pdf", sha)
    db.boletines_mark_extracted(
        conn, boletin_id=b, pages=1, extraction_payload={"pages": []},
        bulletin_number=1, period=None,
        needs_hermes_review=False, entries_matcheables=0,
    )
    db.scans_log_record(conn, kind="hermes", boletin_id=b, status="ok", duration_ms=500)
    db.scans_log_record(conn, kind="hermes", boletin_id=b, status="error", duration_ms=200, detail="timeout")
    conn.commit()
    conn.close()

    from api.main import create_app
    app = create_app()
    def _override_get_db():
        c = db.connect(db_file)
        try:
            yield c
        finally:
            c.close()
    app.dependency_overrides[get_db] = _override_get_db
    cli = TestClient(app)
    token = _token_for(db_file, admin_id, "admin")
    body = cli.get("/api/admin/metrics", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["error_rates"]["hermes"]["total"] == 2
    assert body["error_rates"]["hermes"]["error"] == 1
    assert body["error_rates"]["hermes"]["error_rate_pct"] == 50.0


# ── M.3: latency p50/p95/max ─────────────────────────────────────


def test_metrics_latency_percentiles(client):
    c, db_file, admin_id, _ = client
    token = _token_for(db_file, admin_id, "admin")
    body = c.get("/api/admin/metrics", headers={"Authorization": f"Bearer {token}"}).json()
    lat = body["latency_ms"]
    assert "extract" in lat
    assert lat["extract"]["count"] == 2
    # p50 de [1200, 3000] = 1200, p95 también ~1200 (entero), max=3000
    assert lat["extract"]["p50_ms"] == 1200
    assert lat["extract"]["max_ms"] == 3000


# ── M.4: detecciones por source/confidence/match_kind ────────────


def test_metrics_detecciones_por_source(client):
    c, db_file, admin_id, _ = client
    token = _token_for(db_file, admin_id, "admin")
    body = c.get("/api/admin/metrics", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["detections_by_source"] == {"pdfplumber_text": 1}
    assert body["detections_by_confidence"] == {"high": 1}
    assert body["detections_by_match_kind"] == {"similar": 1}


# ── M.5: cola de Hermes ──────────────────────────────────────────


def test_metrics_hermes_queue(client):
    """needs_hermes_review=1 sin hermes_processed_at cuenta en la cola."""
    c, db_file, admin_id, _ = client
    token = _token_for(db_file, admin_id, "admin")
    body = c.get("/api/admin/metrics", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["hermes_queue"] == 1  # b1 marcado con needs_hermes_review=1


# ── M.6: ultimas_24h y por_boletin ───────────────────────────────


def test_metrics_ultimas_24h_y_por_boletin(client):
    c, db_file, admin_id, _ = client
    token = _token_for(db_file, admin_id, "admin")
    body = c.get("/api/admin/metrics", headers={"Authorization": f"Bearer {token}"}).json()
    u = body["ultimas_24h"]
    assert u["boletines"] == 2
    assert u["detections"] == 1
    assert u["scans_ok"] == 3
    assert u["scans_error"] == 0
    pb = body["detections_por_boletin"]
    assert pb["min"] == 1 and pb["max"] == 1 and pb["avg"] == 1.0
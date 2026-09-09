"""Tests de la Fase 3: seguimiento del expediente de marcas del portfolio."""
from __future__ import annotations

import sqlite3
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from scripts import auth, db
from scripts.expediente import derivar_expediente, estado_from_hit
from scripts.config import Settings
from api.main import create_app
from api.deps import get_db


def _entry(
    expediente: str,
    marca: str,
    *,
    class_nice: int = 25,
    estatus: str | None = None,
    tipo_disposicion: str | None = None,
    disposicion: str | None = None,
    page: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        expediente=expediente,
        marca=marca,
        class_nice=class_nice,
        estatus=estatus,
        tipo_disposicion=tipo_disposicion,
        disposicion=disposicion,
        page=page,
        titular="ACME HOLDINGS LLC",
        tramitante="SAGER MARK G.",
        source="pdfplumber_text",
        matcheable=True,
    )


def _boletin(
    conn: sqlite3.Connection,
    *,
    uploaded_by: int,
    filename: str,
    bulletin_number: int,
    fecha_publicacion: str,
    period: str = "2026-04 (Abril 2026)",
    entries: list[SimpleNamespace],
) -> int:
    bid = db.boletines_create(conn, uploaded_by, filename, f"uploads/{filename}", filename)
    db.boletines_mark_extracted(
        conn, bid, pages=10, extraction_payload={},
        bulletin_number=bulletin_number, period=period,
        needs_hermes_review=False, fecha_publicacion=fecha_publicacion,
    )
    db.boletines_entries_replace(conn, bid, entries)
    return bid


def _user(conn: sqlite3.Connection, email: str, role: str = "propietario") -> db.UserRow:
    uid = db.users_create(conn, email, auth.hash_password("x123456"), role)
    conn.commit()
    return db.users_get(conn, uid)


def test_derivar_por_expediente(tmp_db: sqlite3.Connection):
    user = _user(tmp_db, "a@example.com")
    bid1 = _boletin(
        tmp_db, uploaded_by=user.id, filename="bp652.pdf", bulletin_number=652,
        fecha_publicacion="2026-04-10",
        entries=[_entry("2026-000123", "ACME VENEZUELA", estatus="PUBLICADA", page=5)],
    )
    bid2 = _boletin(
        tmp_db, uploaded_by=user.id, filename="bp654.pdf", bulletin_number=654,
        fecha_publicacion="2026-06-15", period="2026-06 (Junio 2026)",
        entries=[_entry("2026-000123", "ACME VENEZUELA", tipo_disposicion="CONCESION", page=8)],
    )
    pf = db.portfolio_add(tmp_db, user.id, "ACME VENEZUELA", expediente="2026-000123", class_nice=25)
    info = derivar_expediente(tmp_db, db.portfolio_get(tmp_db, pf, user.id), user_id=user.id)

    assert info["estado"] == "CONCEDIDA"
    assert len(info["hitos"]) == 2
    assert info["expedientes"] == ["2026-000123"]
    # Más reciente primero.
    assert info["hitos"][0]["boletin_id"] == bid2
    assert info["hitos"][0]["boletin_period"] == "2026-06 (Junio 2026)"
    assert info["hitos"][0]["boletin_number"] == 654
    assert [{h["boletin_id"], h["expediente"], h["page"]} for h in info["hitos"]] == [
        {bid2, "2026-000123", 8},
        {bid1, "2026-000123", 5},
    ]


def test_estado_por_estatus_sin_disposicion(tmp_db: sqlite3.Connection):
    user = _user(tmp_db, "a@example.com")
    _boletin(
        tmp_db, uploaded_by=user.id, filename="bp652.pdf", bulletin_number=652,
        fecha_publicacion="2026-04-10",
        entries=[_entry("2026-000200", "NOVA TEX", estatus="PUBLICADA")],
    )
    pf = db.portfolio_add(tmp_db, user.id, "NOVA TEX", expediente="2026-000200")
    info = derivar_expediente(tmp_db, db.portfolio_get(tmp_db, pf, user.id), user_id=user.id)
    assert info["estado"] == "PUBLICADA"


def test_fallback_por_nombre_y_clase(tmp_db: sqlite3.Connection):
    user = _user(tmp_db, "a@example.com")
    # La entry usa case distinto del nombre del portfolio; expedientes distintos (UNIQUE constraint).
    _boletin(
        tmp_db, uploaded_by=user.id, filename="bp652.pdf", bulletin_number=652,
        fecha_publicacion="2026-04-10",
        entries=[
            _entry("X-ACME-001", "acme venezuela", class_nice=25, tipo_disposicion="CONCESION"),
            _entry("X-OTRA-002", "OTRA MARCA", class_nice=25, tipo_disposicion="NEGACION"),
        ],
    )
    pf = db.portfolio_add(tmp_db, user.id, "ACME VENEZUELA", class_nice=25)
    info = derivar_expediente(tmp_db, db.portfolio_get(tmp_db, pf, user.id), user_id=user.id)
    assert len(info["hitos"]) == 1
    assert info["estado"] == "CONCEDIDA"
    assert info["marcadas"] == ["acme venezuela"]


def test_excluye_marca_con_error_tipografico(tmp_db: sqlite3.Connection):
    user = _user(tmp_db, "a@example.com")
    pf = db.portfolio_add(tmp_db, user.id, "ACME VENEZUELA", class_nice=25)
    _boletin(
        tmp_db, uploaded_by=user.id, filename="bp652.pdf", bulletin_number=652,
        fecha_publicacion="2026-04-10",
        entries=[_entry("", "ACME VENZUELA", class_nice=25)],
    )
    info = derivar_expediente(tmp_db, db.portfolio_get(tmp_db, pf, user.id), user_id=user.id)
    assert info["hitos"] == []
    assert info["estado"] == "SIN_MOVIMIENTO"


def test_scope_por_usuario_multi_tenant(tmp_db: sqlite3.Connection):
    owner = _user(tmp_db, "owner@example.com", role="propietario")
    outsider = _user(tmp_db, "other@example.com", role="propietario")
    pf = db.portfolio_add(tmp_db, owner.id, "ACME VENEZUELA", expediente="2026-000123")
    _boletin(
        tmp_db, uploaded_by=owner.id, filename="bp652.pdf", bulletin_number=652,
        fecha_publicacion="2026-04-10",
        entries=[_entry("2026-000123", "ACME VENEZUELA", tipo_disposicion="CONCESION")],
    )
    row = db.portfolio_get(tmp_db, pf, owner.id)

    # El dueño ve su boletín.
    assert len(derivar_expediente(tmp_db, row, user_id=owner.id)["hitos"]) == 1
    # Un tercero no ve las apariciones del boletín ajeno.
    assert derivar_expediente(tmp_db, row, user_id=outsider.id)["hitos"] == []
    # Admin (user_id=None) ve todo.
    assert len(derivar_expediente(tmp_db, row, user_id=None)["hitos"]) == 1


def test_alerts_list_filtra_por_portfolio(tmp_db: sqlite3.Connection):
    user = _user(tmp_db, "a@example.com")
    bid = _boletin(
        tmp_db, uploaded_by=user.id, filename="bp652.pdf", bulletin_number=652,
        fecha_publicacion="2026-04-10",
        entries=[_entry("2026-000123", "ACME VENEZUELA", tipo_disposicion="CONCESION")],
    )
    pf1 = db.portfolio_add(tmp_db, user.id, "ACME VENEZUELA", expediente="2026-000123")
    pf2 = db.portfolio_add(tmp_db, user.id, "OTRA MARCA", expediente="2026-000999")
    det1 = db.detections_add(
        tmp_db, boletin_id=bid, user_id=user.id, mark_name="ACME VENEZUELA",
        similarity=1.0, match_kind="own_status", source="pdfplumber_text",
        confidence="high", portfolio_id=pf1, expediente="2026-000123",
    )
    det2 = db.detections_add(
        tmp_db, boletin_id=bid, user_id=user.id, mark_name="OTRA MARCA",
        similarity=1.0, match_kind="own_status", source="pdfplumber_text",
        confidence="high", portfolio_id=pf2, expediente="2026-000999",
    )
    db.alerts_upsert(
        tmp_db, user_id=user.id, detection_id=det1, boletin_id=bid,
        lapse_key="pago_concesion", label="Pago de concesión", marca="ACME VENEZUELA",
        expediente="2026-000123", fecha_publicacion="2026-06-15",
        fecha_limite="2026-07-01", dias_habiles=30,
    )
    db.alerts_upsert(
        tmp_db, user_id=user.id, detection_id=det2, boletin_id=bid,
        lapse_key="oposicion", label="Oposición", marca="OTRA MARCA",
        expediente="2026-000999", fecha_publicacion="2026-06-15",
        fecha_limite="2026-07-15", dias_habiles=30,
    )
    tmp_db.commit()

    rows = db.alerts_list_for_user(tmp_db, user.id, portfolio_id=pf1)
    assert [r.label for r in rows] == ["Pago de concesión"]
    assert db.alerts_list_for_user(tmp_db, user.id, portfolio_id=pf1, estado="pendiente")


def test_estado_from_hit_variants():
    cases = {
        ("PUBLICADA", None): "PUBLICADA",
        (None, "CONCESION"): "CONCEDIDA",
        (None, "NEGACION"): "NEGADA",
        (None, "DEVOLUCION_FORMA"): "DEVUELTA_FORMA",
        (None, "DEVOLUCION_FONDO"): "DEVUELTA_FONDO",
        (None, "CADUCA"): "CADUCA",
        (None, "REVOCA"): "REVOCADA",
        (None, "INADMISIBLE"): "INADMISIBLE",
        ("DESISTIDA", None): "DESISTIDA",
        ("RENOVADA", None): "RENOVADA",
        (None, None): "SOLICITADA",
    }
    for (estatus, tipo), esperado in cases.items():
        assert estado_from_hit(estatus, tipo) == esperado, (estatus, tipo)


# ── API: GET /api/portfolio/{id}/expediente ─────────────────────


@pytest.fixture(autouse=True)
def _patch_settings(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db.init_db(db_file)
    os.environ["SAPI_DB_PATH"] = str(db_file)
    os.environ["JWT_SECRET"] = "test-secret-for-tests"
    os.environ["JWT_EXPIRES_MIN"] = "60"
    os.environ["UPLOADS_DIR"] = str(tmp_path / "uploads")
    os.environ["SERVICE_TOKEN_HERMES"] = ""
    from scripts.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def api_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    db_file = tmp_path / "test_api.db"
    db.init_db(db_file)
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture()
def client(api_db: sqlite3.Connection) -> Iterator[TestClient]:
    app = create_app()

    def _override_get_db():
        yield api_db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c


def test_api_expediente(client: TestClient, api_db: sqlite3.Connection):
    user = _user(api_db, "owner@example.com", role="propietario")
    bid = _boletin(
        api_db, uploaded_by=user.id, filename="bp652.pdf", bulletin_number=652,
        fecha_publicacion="2026-04-10",
        entries=[_entry("2026-000123", "ACME VENEZUELA", tipo_disposicion="CONCESION", page=5)],
    )
    pf = db.portfolio_add(api_db, user.id, "ACME VENEZUELA", expediente="2026-000123", class_nice=25)
    api_db.commit()
    cfg = Settings()
    token = auth.create_access_token(user.id, user.role, secret=cfg.jwt_secret, expires_min=cfg.jwt_expires_min)

    r = client.get(f"/api/portfolio/{pf}/expediente", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado"] == "CONCEDIDA"
    assert body["expedientes"] == ["2026-000123"]
    assert len(body["hitos"]) == 1
    hito = body["hitos"][0]
    assert hito["boletin_number"] == 652
    assert hito["boletin_period"] == "2026-04 (Abril 2026)"
    assert hito["fecha_publicacion"] == "2026-04-10"
    assert hito["page"] == 5
    assert hito["marca"] == "ACME VENEZUELA"

    # El GET alimenta portfolio_history de forma idempotente.
    hist = db.portfolio_history_list(api_db, pf, user.id)
    assert len(hist) == 1
    assert hist[0].boletin_number == 652
    r2 = client.get(f"/api/portfolio/{pf}/expediente", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert len(db.portfolio_history_list(api_db, pf, user.id)) == 1


def test_api_expediente_forbidden(client: TestClient, api_db: sqlite3.Connection):
    owner = _user(api_db, "owner@example.com")
    other = _user(api_db, "other@example.com")
    _boletin(
        api_db, uploaded_by=owner.id, filename="bp652.pdf", bulletin_number=652,
        fecha_publicacion="2026-04-10",
        entries=[_entry("2026-000123", "ACME VENEZUELA")],
    )
    pf = db.portfolio_add(api_db, owner.id, "ACME VENEZUELA", expediente="2026-000123")
    api_db.commit()
    cfg = Settings()
    token = auth.create_access_token(other.id, other.role, secret=cfg.jwt_secret, expires_min=cfg.jwt_expires_min)

    r = client.get(f"/api/portfolio/{pf}/expediente", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (403, 404)


def test_api_expediente_404(client: TestClient, api_db: sqlite3.Connection):
    user = _user(api_db, "owner@example.com")
    api_db.commit()
    cfg = Settings()
    token = auth.create_access_token(user.id, user.role, secret=cfg.jwt_secret, expires_min=cfg.jwt_expires_min)
    r = client.get("/api/portfolio/999/expediente", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404
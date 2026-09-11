"""Tests de Fase 4 de la skill: cola de verificación y envío de veredicto."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from db_utils import connect_readonly, list_verify_queue  # noqa: E402
from verify_queue import main as verify_queue_main  # noqa: E402
from verify_submit import VerifyResult, submit_verdict  # noqa: E402

from conftest import make_boletin  # noqa: E402

from scripts import db  # noqa: E402


def _sheed_flagged(tmp_db, *, verdict=None) -> int:
    """Crea un boletín + una detección marcada para verificar (Fase 4)."""
    bid = make_boletin(tmp_db, filename="BPI_900.pdf")
    did = db.detections_add(
        tmp_db,
        boletin_id=bid,
        user_id=1,
        mark_name="X",
        similarity=0.8,
        match_kind="conflict",
        source="pdfplumber_text",
        confidence="medium",
        needs_hermes_reverify=1,
    )
    if verdict is not None:
        db.detections_verify_set(tmp_db, did, verdict, "motivo de prueba")
    tmp_db.commit()
    return did


def test_queue_lista_candidato_con_contexto(tmp_db, tmp_db_path):
    _sheed_flagged(tmp_db)
    queue = list_verify_queue(tmp_db_path)
    assert len(queue) == 1
    item = queue[0]
    assert item.mark_name == "X"
    assert item.boletin_number == 999
    assert item.match_kind == "conflict"


def test_queue_excluye_ya_verificados(tmp_db, tmp_db_path):
    _sheed_flagged(tmp_db, verdict="discarded")
    assert list_verify_queue(tmp_db_path) == []


def test_queue_respeta_limit(tmp_db, tmp_db_path):
    for i in range(4):
        _sheed_flagged(tmp_db)
    assert len(list_verify_queue(tmp_db_path, limit=2)) == 2


def test_queue_migracion_pendiente_devuelve_vacio(tmp_db_path):
    # Sin columnas de Fase 4 -> [] en lugar de crashear (BD antigua).
    from scripts import db as _db
    conn = _db.connect(tmp_db_path)
    conn.execute("DROP INDEX IF EXISTS idx_detections_verify")
    conn.execute("ALTER TABLE detections DROP COLUMN hermes_verdict")
    conn.execute("ALTER TABLE detections DROP COLUMN hermes_reason")
    conn.execute("ALTER TABLE detections DROP COLUMN hermes_verified_at")
    conn.commit()
    conn.close()
    assert list_verify_queue(tmp_db_path) == []


def test_cli_verify_queue_json(tmp_db, tmp_db_path, capsys):
    _sheed_flagged(tmp_db)
    verify_queue_main(["--db", str(tmp_db_path), "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["mark_name"] == "X"


class FakeResp:
    def __init__(self, status_code: int, data=None):
        self.status_code = status_code
        self._data = data or {}
        self.content = str(data or {}).encode()

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, resp: FakeResp):
        self._resp = resp
        self.last_url = None
        self.last_payload = None
        self.last_headers = None

    def post(self, url, json=None, headers=None):
        self.last_url = url
        self.last_payload = json
        self.last_headers = headers
        return self._resp


def test_submit_verdict_post_correcto():
    client = FakeClient(FakeResp(200, {"hermes_verdict": "confirmed"}))
    res = submit_verdict(7, "confirmed", "conflicto real", api_url="http://x", service_token="tok", client=client)
    assert client.last_url == "http://x/api/detections/7/verify"
    assert client.last_payload == {"verdict": "confirmed", "reason": "conflicto real"}
    assert client.last_headers["X-Hermes-Token"] == "tok"
    assert res.status == "confirmed"
    assert res.http_status == 200


def test_submit_verdict_discarded_ok():
    client = FakeClient(FakeResp(200, {"hermes_verdict": "discarded"}))
    res = submit_verdict(7, "discarded", "falso positivo", api_url="http://x", service_token="tok", client=client)
    assert res.verdict == "discarded"
    assert res.status == "discarded"
    assert res.http_status == 200


def test_submit_verdict_rechaza_invalidos():
    with pytest.raises(ValueError):
        submit_verdict(1, "seguro", "x", api_url="http://x", service_token="tok")
    with pytest.raises(ValueError):
        submit_verdict(1, "confirmed", "", api_url="http://x", service_token="tok")
    with pytest.raises(ValueError):
        submit_verdict(1, "confirmed", "x", api_url="http://x", service_token="")


def test_submit_verdict_error_http_manejado():
    client = FakeClient(FakeResp(503, {}))
    res = submit_verdict(7, "confirmed", "x", api_url="http://x", service_token="tok", client=client)
    assert res.http_status == 503


def test_connect_readonly_no_permite_veredicto(tmp_db_path):
    conn = connect_readonly(tmp_db_path)
    with pytest.raises(Exception):
        conn.execute("UPDATE detections SET hermes_verdict='discarded'")
    conn.close()
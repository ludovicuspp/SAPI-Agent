"""Tests de ``submit.py`` (POST a /api/structured con httpx mockeado)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from submit import StructuredEntry, submit, chunk_entries, _payload_dict  # noqa: E402


class FakeResponse:
    """Réplica mínima de httpx.Response."""

    def __init__(self, status_code: int, data=None, text: str | None = None):
        self.status_code = status_code
        self._data = data or {}
        self.content = (text or "").encode("utf-8")

    def json(self):
        return self._data


class FakeClient:
    """Cliente httpx stub que captura el POST."""

    def __init__(self, response: FakeResponse = None, status: int = 200, data=None):
        self._resp = response or FakeResponse(status, data or {"status": "processed", "entries_added": 2})
        self.last_url = None
        self.last_payload = None
        self.last_headers = None

    def post(self, url, json=None, headers=None):
        self.last_url = url
        self.last_payload = json
        self.last_headers = headers
        return self._resp

    def close(self):
        pass


def _entry(**over):
    base = dict(
        expediente="2015-015976",
        marca="TRIPLE MILLONARIO",
        clase_niza=35,
        titular="RAUL ENRIQUE ARTIGAS",
        estatus="PUBLICADA",
    )
    base.update(over)
    return StructuredEntry(**base)


def test_submit_envia_url_y_headers():
    client = FakeClient()
    submit(1, [_entry()], service_token="tok123", client=client)
    assert client.last_url.endswith("/api/boletines/1/structured")
    assert client.last_headers["X-Hermes-Token"] == "tok123"
    assert client.last_payload["boletin_id"] == 1
    assert len(client.last_payload["entries"]) == 1


def test_submit_error_sin_token():
    with pytest.raises(ValueError):
        submit(1, [_entry()], api_url="http://x", service_token="")


def test_submit_return_ok():
    client = FakeClient(status=200, data={"status": "processed", "entries_added": 2})
    res = submit(1, [_entry(), _entry(marca="ACME")], service_token="t", client=client)
    assert res.http_status == 200
    assert res.status == "processed"
    assert res.entries_added == 2


def test_submit_return_already_processed():
    client = FakeClient(status=200, data={"status": "already_processed", "entries_added": 0})
    res = submit(1, [_entry()], service_token="t", client=client)
    assert res.status == "already_processed"
    assert res.entries_added == 0


def test_submit_error_http_status():
    client = FakeClient(status=503, data={})
    res = submit(1, [_entry()], service_token="t", client=client)
    assert res.http_status == 503


def test_payload_dict_quita_none():
    d = _payload_dict(StructuredEntry(expediente="1", marca="M", clase_niza=25, titular="T"))
    assert "pais" not in d
    assert d["expediente"] == "1"


def test_chunk_entries_respeta_max():
    entries = [_entry(marca=f"M{i}") for i in range(250)]
    chunks = chunk_entries(entries, max_size=100)
    assert [len(c) for c in chunks] == [100, 100, 50]


def test_chunk_entries_default_max():
    entries = [_entry()] * 5
    assert len(chunk_entries(entries)) == 1

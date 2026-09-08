"""Marca un boletín como procesado por Hermes cuando no requiere visión.

POST /api/boletines/{boletin_id}/hermes-done, autenticado con el header
``X-Hermes-Token`` (service token). Se usa cuando el agente determina que
el boletín **no necesita revisión visual** (texto confiable que el parser
Python ya cubrió) o cuando ya terminó el análisis página a página sin
entregar entries nuevas: así el boletín sale de la cola de revisión visual.

Usa la stdlib (``urllib.request``) e imita la API de ``submit.py``. Admite
inyectar un cliente compatible httpx (objeto con
``post(url, json=..., headers=...) -> .status_code, .json()``).

Uso (como archivo):
    python hermes/skills/sapi-monitor/scripts/done.py --boletin-id 27 [--entries-added N]
"""
from __future__ import annotations

import argparse
import json as _json
import os
import urllib.request
from typing import Any, Optional

from _bootstrap import setup_paths, repo_root, load_repo_env

setup_paths()


class _Response:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content

    def json(self):
        if not self.content:
            return {}
        return _json.loads(self.content.decode("utf-8"))


class _UrllibClient:
    """Adaptador mínimo a httpx para el caso por defecto (stdlib)."""

    def post(self, url: str, json=None, headers=None) -> _Response:
        body = _json.dumps(json, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={**(headers or {})})
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                content = resp.read()
                return _Response(resp.status, content)
        except urllib.error.HTTPError as e:
            return _Response(e.code, e.read())


def mark_done(
    boletin_id: int,
    *,
    entries_added: Optional[int] = None,
    api_url: Optional[str] = None,
    service_token: Optional[str] = None,
    client: Optional[Any] = None,
) -> dict[str, Any]:
    """Marca un boletín como procesado por Hermes y devuelve la respuesta."""
    load_repo_env(repo_root())
    api_url = api_url or os.environ.get("HERMES_API_URL", "http://localhost:8000")
    service_token = service_token or os.environ.get("SERVICE_TOKEN_HERMES", "")

    if not service_token:
        raise ValueError("SERVICE_TOKEN_HERMES no está configurado")

    url = f"{api_url.rstrip('/')}/api/boletines/{boletin_id}/hermes-done"
    payload: dict[str, Any] = {"boletin_id": boletin_id}
    if entries_added is not None:
        payload["entries_added"] = entries_added
    headers = {"X-Hermes-Token": service_token}

    c = client or _UrllibClient()
    resp = c.post(url, json=payload, headers=headers)

    data = None
    try:
        data = resp.json()
    except Exception:
        data = {}
    data.setdefault("http_status", int(resp.status_code))
    return data


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Marca un boletín como procesado por Hermes (no-op o fin)."
    )
    parser.add_argument("--boletin-id", required=True, type=int)
    parser.add_argument("--entries-added", type=int, default=None)
    parser.add_argument("--api-url", default=None)
    parser.add_argument("--token", default=None)
    args = parser.parse_args(argv)

    data = mark_done(
        args.boletin_id,
        entries_added=args.entries_added,
        api_url=args.api_url,
        service_token=args.token,
    )
    print(
        f"boletin_id={data.get('boletin_id', args.boletin_id)} "
        f"status={data.get('status')} entries_added={data.get('entries_added')} "
        f"http={data.get('http_status')}"
    )


if __name__ == "__main__":
    main()
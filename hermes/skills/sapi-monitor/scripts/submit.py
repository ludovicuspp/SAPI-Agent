"""Envía las entries estructuradas de Hermes a la API de SAPI-Agent.

POST /api/boletines/{boletin_id}/structured, autenticado con el header
``X-Hermes-Token`` (service token). El endpoint es quien calcula los
match scores (siempre en Python) y marca el boletín como procesado.

La skill NO calcula similitud; solo entrega las entries estructuradas.

Capa de red: usa la stdlib (``urllib.request``) por defecto para no
añadir dependencias. Admite inyectar un cliente compatible httpx
(objeto con ``post(url, json=..., headers=...) -> .status_code, .json()``)
para tests o para reutilizar el cliente de FastAPI/httpx2.

Uso (como archivo):
    python hermes/skills/sapi-monitor/scripts/submit.py --boletin-id 1 --entries e.json
"""
from __future__ import annotations

import argparse
import json as _json
import os
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Optional

from _bootstrap import setup_paths

setup_paths()

MAX_ENTRIES_PER_REQUEST = 100  # límite del endpoint


@dataclass
class StructuredEntry:
    """Espejo del schema ``StructuredEntryIn`` de ``scripts/schemas.py``."""

    expediente: str
    marca: str
    clase_niza: int
    titular: str
    pais: Optional[str] = None
    estatus: str = "PUBLICADA"
    pagina: Optional[int] = None
    fuente: str = "hermes_vision"
    confianza: str = "medium"
    excerpt: Optional[str] = None


@dataclass
class SubmitResult:
    boletin_id: int
    status: str
    entries_added: int
    http_status: int


class _UrllibClient:
    """Adaptador mínimo a httpx para el caso por defecto (stdlib)."""

    def post(self, url: str, json=None, headers=None) -> "_Response":
        body = _json.dumps(json, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={**(headers or {})})
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                content = resp.read()
                return _Response(resp.status, content)
        except urllib.error.HTTPError as e:
            return _Response(e.code, e.read())


class _Response:
    """Réplica de la API mínima de httpx.Response usada aquí."""

    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content

    def json(self):
        if not self.content:
            return {}
        return _json.loads(self.content.decode("utf-8"))


def _payload_dict(entry: StructuredEntry) -> dict[str, Any]:
    d = asdict(entry)
    # Quitar claves None para no romper la validación estricta del schema.
    return {k: v for k, v in d.items() if v is not None}


def submit(
    boletin_id: int,
    entries: list[StructuredEntry],
    *,
    api_url: Optional[str] = None,
    service_token: Optional[str] = None,
    client: Optional[Any] = None,
) -> SubmitResult:
    """Envía entries a la API y devuelve el resultado.

    ``api_url`` y ``service_token`` se toman de env si no se pasan
    (``HERMES_API_URL`` y ``SERVICE_TOKEN_HERMES``). ``client`` debe
    exponer ``post(url, json=..., headers=...) -> .status_code, .json()``
    (por defecto usa la stdlib).
    """
    api_url = api_url or os.environ.get("HERMES_API_URL", "http://localhost:8000")
    service_token = service_token or os.environ.get("SERVICE_TOKEN_HERMES", "")

    if not service_token:
        raise ValueError("SERVICE_TOKEN_HERMES no está configurado")

    url = f"{api_url.rstrip('/')}/api/boletines/{boletin_id}/structured"
    payload = {
        "boletin_id": boletin_id,
        "entries": [_payload_dict(e) for e in entries],
    }
    headers = {"X-Hermes-Token": service_token}

    c = client or _UrllibClient()
    resp = c.post(url, json=payload, headers=headers)

    data = None
    try:
        data = resp.json()
    except Exception:
        data = {}
    return SubmitResult(
        boletin_id=boletin_id,
        status=str(data.get("status", resp.status_code)),
        entries_added=int(data.get("entries_added", 0)),
        http_status=int(resp.status_code),
    )


def chunk_entries(
    entries: list[StructuredEntry], max_size: int = MAX_ENTRIES_PER_REQUEST
) -> list[list[StructuredEntry]]:
    """Divide la lista en trozos que respetan el límite del endpoint."""
    return [entries[i : i + max_size] for i in range(0, len(entries), max_size)]


def _entry_from_dict(d: dict[str, Any]) -> StructuredEntry:
    known = {f for f in StructuredEntry.__dataclass_fields__}  # type: ignore[attr-defined]
    return StructuredEntry(**{k: v for k, v in d.items() if k in known})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Envía entries estructuradas a la API de SAPI-Agent."
    )
    parser.add_argument("--boletin-id", required=True, type=int)
    parser.add_argument(
        "--entries", required=True, help="Ruta a JSON: lista de dicts de StructuredEntry"
    )
    parser.add_argument("--api-url", default=None)
    parser.add_argument("--token", default=None)
    args = parser.parse_args(argv)

    with open(args.entries, encoding="utf-8") as fh:
        raw = _json.load(fh)
    entries = [_entry_from_dict(d) for d in raw]

    result = submit(
        args.boletin_id,
        entries,
        api_url=args.api_url,
        service_token=args.token,
    )
    print(
        f"boletin_id={result.boletin_id} status={result.status} "
        f"entries_added={result.entries_added} http={result.http_status}"
    )


if __name__ == "__main__":
    main()

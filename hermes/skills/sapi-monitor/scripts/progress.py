"""Reporta el avance página a página de Hermes a la API de SAPI-Agent.

POST /api/boletines/{boletin_id}/hermes-progress, autenticado con el
header ``X-Hermes-Token`` (service token). El boletín debe estar
``extracted`` con ``needs_hermes_review=1`` y aún sin
``hermes_processed_at``.

Usa la stdlib (``urllib.request``) e imita la API de `submit.py`. Admite
inyectar un cliente compatible httpx (objeto con
``post(url, json=..., headers=...) -> .status_code, .json()``).

Uso (como archivo):
    python hermes/skills/sapi-monitor/scripts/progress.py \
      --boletin-id 27 --step analyzing_page --current-page 512 --total-pages 1852
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
    """Réplica de la API mínima de httpx.Response usada aquí."""

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


def report_progress(
    boletin_id: int,
    *,
    step: Optional[str] = None,
    current_page: Optional[int] = None,
    total_pages: Optional[int] = None,
    api_url: Optional[str] = None,
    service_token: Optional[str] = None,
    client: Optional[Any] = None,
) -> dict[str, Any]:
    """Envia un heartbeat de progreso de Hermes y devuelve la respuesta.

    ``api_url`` y ``service_token`` se toman de env si no se pasan
    (``HERMES_API_URL`` y ``SERVICE_TOKEN_HERMES``). ``client`` debe
    exponer ``post(url, json=..., headers=...) -> .status_code, .json()``.
    """
    load_repo_env(repo_root())
    api_url = api_url or os.environ.get("HERMES_API_URL", "http://localhost:8000")
    service_token = service_token or os.environ.get("SERVICE_TOKEN_HERMES", "")

    if not service_token:
        raise ValueError("SERVICE_TOKEN_HERMES no está configurado")

    url = f"{api_url.rstrip('/')}/api/boletines/{boletin_id}/hermes-progress"
    payload: dict[str, Any] = {"boletin_id": boletin_id}
    if step is not None:
        payload["step"] = step
    if current_page is not None:
        payload["current_page"] = current_page
    if total_pages is not None:
        payload["total_pages"] = total_pages
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
        description="Reporta el avance página a página de Hermes a la API."
    )
    parser.add_argument("--boletin-id", required=True, type=int)
    parser.add_argument("--step", default=None, help="Etapa (ej. analyzing_page, done)")
    parser.add_argument("--current-page", type=int, default=None)
    parser.add_argument("--total-pages", type=int, default=None)
    parser.add_argument("--api-url", default=None)
    parser.add_argument("--token", default=None)
    args = parser.parse_args(argv)

    data = report_progress(
        args.boletin_id,
        step=args.step,
        current_page=args.current_page,
        total_pages=args.total_pages,
        api_url=args.api_url,
        service_token=args.token,
    )
    print(
        f"boletin_id={data.get('boletin_id', args.boletin_id)} "
        f"step={data.get('step')} current_page={data.get('current_page')} "
        f"total_pages={data.get('total_pages')} http={data.get('http_status')}"
    )


if __name__ == "__main__":
    main()
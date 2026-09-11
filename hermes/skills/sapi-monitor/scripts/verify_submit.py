"""Envía el veredicto de verificación de un conflicto a la API (Fase 4).

POST /api/detections/{id}/verify, autenticado con ``X-Hermes-Token``.
El veredicto es BINARIO y con motivo: ``confirmed`` (el conflicto es
real) o ``discarded`` (falso positivo). Hermes NO recalcula similitud:
solo confirma o descarta la decisión del matcher Python. Un ``discarded``
oculta la detección del listado accionable y descarta sus alertas
pendientes.

Capa de red: stdlib (``urllib.request``), como ``submit.py``. Acepta un
cliente inyectable (``post(url, json=..., headers=...)``) para tests.

Uso (como archivo):
    python hermes/skills/sapi-monitor/scripts/verify_submit.py \
      --detection-id 42 --verdict discarded --reason "Marca corta, no relacionada"
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any, Optional

from _bootstrap import setup_paths, repo_root, load_repo_env

setup_paths()

from submit import _UrllibClient  # noqa: E402  (reutiliza adaptador stdlib)


@dataclass
class VerifyResult:
    detection_id: int
    verdict: str
    status: str
    http_status: int


def submit_verdict(
    detection_id: int,
    verdict: str,
    reason: str,
    *,
    api_url: Optional[str] = None,
    service_token: Optional[str] = None,
    client: Optional[Any] = None,
) -> VerifyResult:
    """Envía el veredicto a la API y devuelve el resultado.

    ``api_url`` y ``service_token`` se toman del env si no se pasan.
    ``verdict`` solo admite ``confirmed`` / ``discarded``.
    """
    if verdict not in ("confirmed", "discarded"):
        raise ValueError("verdict debe ser 'confirmed' o 'discarded'")
    if not (reason or "").strip():
        raise ValueError("reason es obligatoria")

    load_repo_env(repo_root())
    if api_url is None:
        api_url = os.environ.get("HERMES_API_URL", "http://localhost:8000")
    if service_token is None:
        service_token = os.environ.get("SERVICE_TOKEN_HERMES", "")

    if not service_token:
        raise ValueError("SERVICE_TOKEN_HERMES no está configurado")

    url = f"{api_url.rstrip('/')}/api/detections/{detection_id}/verify"
    payload = {"verdict": verdict, "reason": reason}
    headers = {"X-Hermes-Token": service_token}

    c = client or _UrllibClient()
    resp = c.post(url, json=payload, headers=headers)

    data = {}
    try:
        data = resp.json()
    except Exception:
        data = {}
    return VerifyResult(
        detection_id=detection_id,
        verdict=verdict,
        status=str(data.get("hermes_verdict", resp.status_code)),
        http_status=int(resp.status_code),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Envía el veredicto de verificación de un conflicto a la API."
    )
    parser.add_argument("--detection-id", required=True, type=int)
    parser.add_argument("--verdict", required=True, choices=["confirmed", "discarded"])
    parser.add_argument("--reason", required=True, help="Motivo corto del veredicto")
    parser.add_argument("--api-url", default=None)
    parser.add_argument("--token", default=None)
    args = parser.parse_args(argv)

    result = submit_verdict(
        args.detection_id,
        args.verdict,
        args.reason,
        api_url=args.api_url,
        service_token=args.token,
    )
    print(
        f"detection_id={result.detection_id} verdict={result.verdict} "
        f"status={result.status} http={result.http_status}"
    )


if __name__ == "__main__":
    main()
"""CLI: lista boletines pendientes de revisión visual de Hermes.

Imprime por stdout un resumen consumible por el agente o por un
``--monitor-script`` del cron. Siempre read-only.

Uso (como archivo):
    python hermes/skills/sapi-monitor/scripts/pending_boletines.py [--db PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import setup_paths, repo_db_path

setup_paths()

from db_utils import list_pending_hermes  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Lista boletines pendientes de revisión visual de Hermes."
    )
    parser.add_argument("--db", default=None, help="Ruta a data/sapi.db (default: repo)")
    parser.add_argument("--limit", type=int, default=50, help="Máx. boletines a listar")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    args = parser.parse_args(argv)

    db_path = args.db or repo_db_path()

    if not Path(db_path).exists():
        if args.json:
            print("[]")
        else:
            print("Sin boletines pendientes de revisión visual.")
        return

    pending = list_pending_hermes(db_path, limit=args.limit)

    if args.json:
        print(json.dumps([p.__dict__ for p in pending], ensure_ascii=False, indent=2))
        return

    if not pending:
        print("Sin boletines pendientes de revisión visual.")
        return

    print(f"{len(pending)} boletín(es) pendiente(s) de revisión visual:\n")
    for p in pending:
        print(
            f"  #{p.boletin_id}  {p.filename}  "
            f"(páginas: {p.total_pages}, con imagen: {p.pages_with_images}, "
            f"texto bajo: {p.pages_low_confidence})"
        )


if __name__ == "__main__":
    main()

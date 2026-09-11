"""CLI: lista la cola de verificación de conflictos (Fase 4).

Detecciones borderline (marcas cortas, confianza media/baja, familia de
marca) que Hermes debe confirmar o descartar para reducir falsos
positivos. Solo lectura de SQLite; el veredicto se entrega a la API con
``verify_submit.py``.

Uso (como archivo):
    python hermes/skills/sapi-monitor/scripts/verify_queue.py [--db PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import setup_paths, repo_db_path

setup_paths()

from db_utils import list_verify_queue  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Lista la cola de verificación de conflictos de Hermes."
    )
    parser.add_argument("--db", default=None, help="Ruta a data/sapi.db (default: repo)")
    parser.add_argument("--limit", type=int, default=50, help="Máx. candidatos a listar")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    args = parser.parse_args(argv)

    db_path = args.db or repo_db_path()

    if not Path(db_path).exists():
        if args.json:
            print("[]")
        else:
            print("Sin candidatos de verificación de conflictos.")
        return

    queue = list_verify_queue(db_path, limit=args.limit)

    if args.json:
        print(json.dumps([q.__dict__ for q in queue], ensure_ascii=False, indent=2))
        return

    if not queue:
        print("Sin candidatos de verificación de conflictos.")
        return

    print(f"{len(queue)} candidato(s) a verificación de conflictos:\n")
    for q in queue:
        print(
            f"  #{q.id}  {q.mark_name}  (match: {q.matched_with or '-'}, "
            f"clase {q.class_nice or '-'}, sim {q.similarity:.2f}, "
            f"{q.confidence}, {q.match_kind}, boletín {q.boletin_number or q.boletin_id})"
        )


if __name__ == "__main__":
    main()
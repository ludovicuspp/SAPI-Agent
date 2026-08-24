"""CLI de SAPI-Agent.

Entry points::

    python -m scripts.cli init-db
    python -m scripts.cli create-user --email ... --password ... --role admin|agent
    python -m scripts.cli add-watchlist --user-email ... --name ... [--class-nice N]
    python -m scripts.cli list-watchlist --user-email ...
    python -m scripts.cli add-portfolio --user-email ... --name ... [--expediente ...]
    python -m scripts.cli process-boletin PATH --user-email ... [--notify/--no-notify]
    python -m scripts.cli list-detections --user-email ... [--limit N]
    python -m scripts.cli send-digest --user-email ...
    python -m scripts.cli stats --user-email ...
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import warnings
from pathlib import Path

from scripts.auth import hash_password
from scripts.config import get_settings
from scripts.db import (
    connect,
    init_db,
    portfolio_add,
    portfolio_list_for_user,
    stats_for_user,
    users_count_admins,
    users_create,
    users_get_by_email,
    watchlist_add,
    watchlist_list_for_user,
)
from scripts.notifiers import email_smtp
from scripts.db import (
    DetectionRow,
    boletines_get,
    detections_list_for_user,
    detections_mark_notified,
    detections_pending_notification,
)
from scripts.orchestration import processor


# ── helpers ────────────────────────────────────────────────────


def _load_conn():
    cfg = get_settings()
    Path(cfg.sapi_db_path).parent.mkdir(parents=True, exist_ok=True)
    return cfg, connect(cfg.sapi_db_path)


def _resolve_user(conn, email: str):
    user = users_get_by_email(conn, email)
    if user is None:
        print(f"ERROR: no existe el usuario '{email}'.", file=sys.stderr)
        sys.exit(2)
    return user


def _print_table(headers, rows):
    widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "  ".join("-" * w for w in widths)
    print(line)
    print(sep)
    for r in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)))


# ── subcomandos ────────────────────────────────────────────────


def cmd_init_db(args):
    cfg, _ = _load_conn()
    init_db(cfg.sapi_db_path)
    print(f"OK: esquema SQLite creado en {cfg.sapi_db_path}")

    # Seed admin si ADMIN_EMAIL/ADMIN_PASSWORD están en .env y no hay admins.
    conn = connect(cfg.sapi_db_path)
    try:
        if users_count_admins(conn) == 0 and cfg.admin_email and cfg.admin_password:
            users_create(
                conn,
                email=cfg.admin_email,
                password_hash=hash_password(cfg.admin_password),
                role="admin",
            )
            conn.commit()
            print(
                f"OK: usuario admin inicial '{cfg.admin_email}' creado desde .env."
            )
        elif users_count_admins(conn) == 0:
            print(
                "AVISO: no se creó admin inicial; define ADMIN_EMAIL y "
                "ADMIN_PASSWORD en .env, o créalo manualmente con "
                "`python -m scripts.cli create-user --role admin`."
            )
    finally:
        conn.close()


def cmd_create_user(args):
    cfg, conn = _load_conn()
    try:
        email = args.email
        password = args.password
        if not password and not args.password_from_stdin:
            password = getpass.getpass("Contraseña: ")
            confirm = getpass.getpass("Confirma: ")
            if password != confirm:
                print("ERROR: las contraseñas no coinciden.", file=sys.stderr)
                sys.exit(2)
        if args.password_from_stdin:
            password = sys.stdin.readline().rstrip("\n")

        if users_get_by_email(conn, email):
            print(f"ERROR: ya existe '{email}'.", file=sys.stderr)
            sys.exit(2)

        user_id = users_create(
            conn,
            email=email,
            password_hash=hash_password(password),
            role=args.role,
        )
        conn.commit()
        print(f"OK: usuario '{email}' (id={user_id}, role={args.role}) creado.")
    finally:
        conn.close()


def cmd_add_watchlist(args):
    cfg, conn = _load_conn()
    try:
        user = _resolve_user(conn, args.user_email)
        wid = watchlist_add(
            conn,
            user_id=user.id,
            name=args.name,
            class_nice=args.class_nice,
            notes=args.notes,
        )
        conn.commit()
        print(f"OK: marca vigilada '{args.name}' (id={wid}) añadida.")
    finally:
        conn.close()


def cmd_list_watchlist(args):
    cfg, conn = _load_conn()
    try:
        user = _resolve_user(conn, args.user_email)
        items = watchlist_list_for_user(conn, user.id, only_active=args.only_active)
        if not items:
            print("(sin marcas vigiladas)")
            return
        rows = [
            (w.id, w.name, w.class_nice or "-", "sí" if w.active else "no",
             w.created_at)
            for w in items
        ]
        _print_table(["ID", "Nombre", "Clase", "Activa", "Creada"], rows)
    finally:
        conn.close()


def cmd_add_portfolio(args):
    cfg, conn = _load_conn()
    try:
        user = _resolve_user(conn, args.user_email)
        pid = portfolio_add(
            conn,
            user_id=user.id,
            name=args.name,
            expediente=args.expediente,
            class_nice=args.class_nice,
            notes=args.notes,
        )
        conn.commit()
        print(f"OK: marca de portafolio '{args.name}' (id={pid}) añadida.")
    finally:
        conn.close()


def cmd_list_portfolio(args):
    cfg, conn = _load_conn()
    try:
        user = _resolve_user(conn, args.user_email)
        items = portfolio_list_for_user(conn, user.id)
        if not items:
            print("(sin marcas en portafolio)")
            return
        rows = [
            (p.id, p.name, p.expediente or "-", p.class_nice or "-",
             p.status or "-", p.last_checked_at or "-")
            for p in items
        ]
        _print_table(
            ["ID", "Nombre", "Expediente", "Clase", "Último estatus", "Revisado"],
            rows,
        )
    finally:
        conn.close()


def cmd_process_boletin(args):
    cfg, conn = _load_conn()
    try:
        user = _resolve_user(conn, args.user_email)
        result = processor.process_pdf(
            Path(args.path),
            user_id=user.id,
            conn=conn,
            settings=cfg,
            notify=args.notify,
        )
        conn.commit()
        print(
            f"OK: boletín procesado (id={result.boletin_id})\n"
            f"  Boletín:      #{result.bulletin_number or '?'} ({result.period or '?'})\n"
            f"  Páginas:      {result.pages_extracted}/{result.pages_total}\n"
            f"  Entries:      {result.entries_parsed}\n"
            f"  Detecciones:  {result.detections_created}\n"
            f"  Hermes pend.: {'sí' if result.needs_hermes_review else 'no'}\n"
            f"  Emails:       {result.emailed} enviados, {result.email_failed} fallidos\n"
            f"  Duración:     {result.duration_ms} ms"
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    finally:
        conn.close()


def cmd_list_detections(args):
    cfg, conn = _load_conn()
    try:
        user = _resolve_user(conn, args.user_email)
        items = detections_list_for_user(conn, user.id, limit=args.limit)
        if not items:
            print("(sin detecciones)")
            return
        rows = [
            (
                d.id,
                d.boletin_id,
                d.mark_name,
                d.expediente or "-",
                d.class_nice or "-",
                f"{d.similarity * 100:.1f}%",
                d.source,
                d.confidence,
                d.match_kind,
            )
            for d in items
        ]
        _print_table(
            ["ID", "Boletín", "Marca", "Expediente", "Clase",
             "Similitud", "Fuente", "Conf.", "Tipo"],
            rows,
        )
    finally:
        conn.close()


def cmd_send_digest(args):
    cfg, conn = _load_conn()
    try:
        user = _resolve_user(conn, args.user_email)
        pending = detections_pending_notification(conn, user.id, limit=500)
        if not pending:
            print("No hay detecciones pendientes de notificación.")
            return
        boletines_ids = {d.boletin_id for d in pending}
        boletines_map = {
            b.id: b for b in (boletines_get(conn, bid) for bid in boletines_ids)
            if b is not None
        }
        subject, html = email_smtp.render_digest(
            pending, boletines_map, period_label=args.period_label
        )
        if not cfg.smtp_configured:
            print("AVISO: SMTP no configurado; muestro resumen en pantalla:")
            print(f"Asunto: {subject}")
            print(html)
            return
        delivery = email_smtp.send_detection_emails(
            to_address=user.email,
            detections=pending,
            boletines_by_id=boletines_map,
            settings=cfg,
        )
        detections_mark_notified(conn, delivery.sent)
        conn.commit()
        print(
            f"OK: digest enviado a {user.email} "
            f"({delivery.sent} ok, {len(delivery.failed)} fallidos)."
        )
    finally:
        conn.close()


def cmd_stats(args):
    cfg, conn = _load_conn()
    try:
        user = _resolve_user(conn, args.user_email)
        s = stats_for_user(conn, user.id)
        print(f"Estadísticas para {user.email} ({user.role}):")
        print(f"  Marcas vigiladas:  {s.watchlist_count}")
        print(f"  Marcas portafolio: {s.portfolio_count}")
        print(f"  Boletines:         {s.boletines_count}")
        print(f"  Detecciones:       {s.detections_count}")
        print(f"  Último boletín:    {s.last_boletin_at or '—'}")
    finally:
        conn.close()


# ── argparse ───────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts.cli",
        description="SAPI-Agent: CLI de monitoreo de marcas.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Crea el esquema SQLite (idempotente).")

    s = sub.add_parser("create-user", help="Crea un usuario.")
    s.add_argument("--email", required=True)
    s.add_argument("--password", help="Contraseña en claro (no recomendado)")
    s.add_argument(
        "--password-from-stdin",
        action="store_true",
        help="Lee la contraseña de stdin",
    )
    s.add_argument(
        "--role",
        choices=["admin", "agent"],
        default="agent",
        help="Rol del usuario",
    )

    s = sub.add_parser("add-watchlist", help="Añade una marca vigilada.")
    s.add_argument("--user-email", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--class-nice", type=int)
    s.add_argument("--notes")

    s = sub.add_parser("list-watchlist", help="Lista la watchlist del usuario.")
    s.add_argument("--user-email", required=True)
    s.add_argument(
        "--only-active",
        action="store_true",
        default=True,
        help="Solo marcas activas (por defecto)",
    )

    s = sub.add_parser("add-portfolio", help="Añade una marca al portafolio.")
    s.add_argument("--user-email", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--expediente")
    s.add_argument("--class-nice", type=int)
    s.add_argument("--notes")

    s = sub.add_parser("list-portfolio", help="Lista el portafolio del usuario.")
    s.add_argument("--user-email", required=True)

    s = sub.add_parser(
        "process-boletin", help="Procesa un PDF de boletín end-to-end."
    )
    s.add_argument("path", help="Ruta al PDF")
    s.add_argument("--user-email", required=True)
    s.add_argument(
        "--notify",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Si se envía email de las nuevas detecciones",
    )

    s = sub.add_parser("list-detections", help="Lista las detecciones.")
    s.add_argument("--user-email", required=True)
    s.add_argument("--limit", type=int, default=50)

    s = sub.add_parser("send-digest", help="Envía resumen por email.")
    s.add_argument("--user-email", required=True)
    s.add_argument("--period-label")

    s = sub.add_parser("stats", help="Estadísticas del usuario.")
    s.add_argument("--user-email", required=True)

    return p


def main(argv: list[str] | None = None) -> int:
    warnings.filterwarnings("default")
    args = build_parser().parse_args(argv)
    dispatch = {
        "init-db": cmd_init_db,
        "create-user": cmd_create_user,
        "add-watchlist": cmd_add_watchlist,
        "list-watchlist": cmd_list_watchlist,
        "add-portfolio": cmd_add_portfolio,
        "list-portfolio": cmd_list_portfolio,
        "process-boletin": cmd_process_boletin,
        "list-detections": cmd_list_detections,
        "send-digest": cmd_send_digest,
        "stats": cmd_stats,
    }
    dispatch[args.cmd](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

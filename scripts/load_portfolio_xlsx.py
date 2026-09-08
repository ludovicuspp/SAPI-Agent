"""Carga el XLSX de portfolio al sistema para el usuario Luis Vargas.

Convierte el Excel de marcas al formato normalizado del sistema y aplica
el import (upsert por #REGISTRO/#SOLICITUD) usando el pipeline real
(scripts/portfolio_import).
"""
import sys
from datetime import datetime

import openpyxl

sys.path.insert(0, ".")
from scripts import portfolio_import, db

XLSX = "data/uploads/portafolio_marcas_2024.xlsx"
USER_EMAIL = "luis.vargas@ironflexgroup.com"

# PAIS: VE->Venezuela, CH->?, USA->?, CO->Colombia
PAIS_MAP = {
    "VE": "Venezuela",
    "CO": "Colombia",
    "CH": "Chile",
}
ESTADO_MAP = {
    "REGISTRADA": "Registrada",
    "DESISTIDA": "Desistida",
    "ABANDONADA": "Abandonada",
    "NEGADA": "Negada",
    "NEGADA / RECONSIDERACIÓN": "Negada",
    "PENDIENTE": "Pendiente Resolución",
    "PENDIENTE RESOLUCIÓN": "Pendiente Resolución",
    "EXAMEN DE FONDO": "Pendiente Resolución",
    "None": "Pendiente Resolución",
}
TIPO_MAP = {
    "MIXTA": "Mixta",
    "DENOMINATIVA": "Denominativa",
    "GRÁFICA": "Grafica",
    "GRAFICA": "Grafica",
}


def fmt_date(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, (int, float)):
        try:
            return datetime.fromordinal(datetime(1899, 12, 30).toordinal() + int(v)).strftime("%Y-%m-%d")
        except Exception:
            return None
    return None


def main():
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb.active

    rows = []
    skipped = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        if r[1] is None and r[0] is None:
            continue
        marca = (r[1] or "").strip()
        if not marca:
            skipped.append((i + 1, "sin marca"))
            continue

        est_excel = ("%s" % r[2]) if r[2] else "None"
        estado = ESTADO_MAP.get(est_excel.strip().upper(), "Pendiente Resolución")

        # ESTADO II -> empresa licenciada SOLO si es licencia
        e2 = str(r[15]).strip() if r[15] else ""
        empresa_lic = None
        if "LICENCIA" in e2.upper():
            empresa_lic = e2

        # Comentarios: COMENTARIOS I + II
        c1 = str(r[16]).strip() if r[16] else ""
        c2 = str(r[17]).strip() if r[17] else ""
        comentarios = "; ".join(x for x in (c1, c2) if x) or None

        pais = PAIS_MAP.get(str(r[0]).strip().upper(), str(r[0]).strip().upper() or "Venezuela")

        rows.append({
            "name": marca,
            "pais": pais,
            "status": estado,
            "tipo_registro": TIPO_MAP.get(str(r[4]).strip().upper(), str(r[4]).strip() or None),
            "bufete": str(r[5]).strip() if r[5] else None,
            "solicitud": str(r[6]).strip() if r[6] else None,
            "fecha_solicitud": fmt_date(r[7]),
            "registro": str(r[8]).strip() if r[8] else None,
            "fecha_registro": fmt_date(r[9]),
            "fecha_vencimiento": fmt_date(r[10]),
            "class_nice": int(r[11]) if isinstance(r[11], (int, float)) and r[11] else (str(r[11]).strip() if r[11] else None),
            # etiqueta (col 3): no se transfiere de excel
            "productos_servicios": str(r[12]).strip() if r[12] else None,
            "titular": str(r[13]).strip() if r[13] else None,
            "tramitante": str(r[14]).strip() if r[14] else None,
            "empresa_licenciada": empresa_lic,
            "comentarios": comentarios,
        })
    wb.close()

    print(f"Filas leídas: {len(rows)}")
    for line, reason in skipped:
        print(f"  omitida L{line}: {reason}")
    if not rows:
        print("Nada que importar.")
        return 1

    # Guardar CSV de respaldo en formato plantilla (por si se quiere revisar)
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(portfolio_import.TEMPLATE_HEADERS)
    for r in rows:
        w.writerow([
            r["pais"], r["name"], r["status"], "", r["tipo_registro"], r["bufete"],
            r["solicitud"], r["fecha_solicitud"], r["registro"], r["fecha_registro"],
            r["fecha_vencimiento"], r["class_nice"], r["productos_servicios"],
            r["titular"], r["tramitante"], r["empresa_licenciada"], r["comentarios"],
        ])
    with open("/tmp/opencode/portfolio_luis_vargas.csv", "w", encoding="utf-8-sig") as f:
        f.write(buf.getvalue())

    # Aplicar import a la BD real
    conn = db.connect("data/sapi.db")
    user = db.users_get_by_email(conn, USER_EMAIL)
    if user is None:
        print(f"ERROR: usuario {USER_EMAIL} no existe")
        conn.close()
        return 1
    result = portfolio_import.apply_import(conn, user.id, rows)
    conn.commit()
    total = len(db.portfolio_list_for_user(conn, user.id))
    conn.close()
    print(f"Creadas: {result.created}, actualizadas: {result.updated}, filas: {len(rows)}")
    print(f"Total dec.portfolio del usuario: {total}")
    for e in result.errors[:20]:
        print("  ERROR:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

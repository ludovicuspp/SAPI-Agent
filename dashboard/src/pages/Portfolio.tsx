import { useEffect, useState } from "react";
import { request, uploadFile, getToken } from "@/lib/api";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { Portfolio, PortfolioHistory, PortfolioImportResult } from "@/types/api";

const ESTADOS = ["Registrada", "Pendiente Resolución", "Desistida", "Abandonada", "Negada"];
const TIPOS = ["Mixta", "Denominativa", "Grafica"];

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function emptyForm(p?: Portfolio) {
  return {
    name: p?.name ?? "",
    expediente: p?.expediente ?? "",
    class_nice: p?.class_nice != null ? String(p.class_nice) : "",
    status: p?.status ?? "Pendiente Resolución",
    pais: p?.pais ?? "Venezuela",
    etiqueta: p?.etiqueta ?? "",
    tipo_registro: p?.tipo_registro ?? "",
    bufete: p?.bufete ?? "",
    solicitud: p?.solicitud ?? "",
    fecha_solicitud: p?.fecha_solicitud ?? "",
    registro: p?.registro ?? "",
    fecha_registro: p?.fecha_registro ?? "",
    fecha_vencimiento: p?.fecha_vencimiento ?? "",
    titular: p?.titular ?? "",
    tramitante: p?.tramitante ?? "",
    empresa_licenciada: p?.empresa_licenciada ?? "",
    productos_servicios: p?.productos_servicios ?? "",
    comentarios: p?.comentarios ?? "",
  };
}

type Form = ReturnType<typeof emptyForm>;

export default function PortfolioPage() {
  const [items, setItems] = useState<Portfolio[]>([]);
  const [selected, setSelected] = useState<Portfolio | null>(null);
  const [form, setForm] = useState<Form>(emptyForm());
  const [history, setHistory] = useState<PortfolioHistory[] | null>(null);
  const [message, setMessage] = useState("");
  const [importMsg, setImportMsg] = useState("");
  const [etiquetaFile, setEtiquetaFile] = useState<File | null>(null);

  const load = () => request<Portfolio[]>("/api/portfolio").then(setItems).catch(console.error);
  useEffect(() => { load(); }, []);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const openNew = () => {
    setSelected(null);
    setForm(emptyForm());
    setHistory(null);
    setMessage("");
  };

  const openDetail = (p: Portfolio) => {
    setSelected(p);
    setForm(emptyForm(p));
    setHistory(null);
    setMessage("");
    request<PortfolioHistory[]>(`/api/portfolio/${p.id}/history`)
      .then(setHistory)
      .catch(() => setHistory([]));
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload = { ...form, class_nice: form.class_nice ? Number(form.class_nice) : null };
    const path = selected ? `/api/portfolio/${selected.id}` : "/api/portfolio";
    await request<Portfolio>(path, { method: selected ? "PUT" : "POST", body: JSON.stringify(payload) });
    if (etiquetaFile && selected) {
      try {
        await uploadFile<Portfolio>(`/api/portfolio/${selected.id}/etiqueta`, etiquetaFile);
        setEtiquetaFile(null);
      } catch (err) {
        setMessage(err instanceof Error ? `Etiqueta: ${err.message}` : "Error subiendo etiqueta");
      }
    }
    setMessage("Guardado correctamente.");
    load();
    if (selected) openDetail({ ...selected, ...payload } as Portfolio);
  };

  const downloadTemplate = async () => {
    const res = await fetch(`${API_BASE}/api/portfolio/template`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "portfolio_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const importCsv = async (file: File) => {
    try {
      const r = await uploadFile<PortfolioImportResult>("/api/portfolio/import", file);
      setImportMsg(`Creadas: ${r.created}, actualizadas: ${r.updated}${r.errors.length ? `, errores: ${r.errors.length}` : ""}`);
      load();
    } catch (err) {
      setImportMsg(err instanceof Error ? err.message : "Error al importar");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Portfolio</h1>
        <div className="flex gap-2">
          <label className="text-sm">
            <Button type="button" variant="outline" size="sm">
              Importar CSV
            </Button>
            <input type="file" accept=".csv" className="hidden" onChange={(e) => e.target.files?.[0] && importCsv(e.target.files[0])} />
          </label>
          <Button type="button" variant="outline" size="sm" onClick={downloadTemplate}>
            Descargar plantilla
          </Button>
          <Button type="button" size="sm" onClick={openNew}>
            Nueva marca
          </Button>
        </div>
      </div>

      {importMsg && <div className="text-sm text-blue-600">{importMsg}</div>}

      <Card>
        <CardHeader>
          <CardTitle>{selected ? `Marca: ${form.name || "—"}` : "Alta de marca"}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={save} className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Input placeholder="MARCA *" value={form.name} onChange={set("name")} className="min-w-40 flex-1" />
              <Input placeholder="Clase Niza" value={form.class_nice} onChange={set("class_nice")} className="w-24" />
              <Input placeholder="PAÍS" value={form.pais} onChange={set("pais")} className="w-32" />
              <select className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={form.status} onChange={set("status")}>
                {ESTADOS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <select className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={form.tipo_registro} onChange={set("tipo_registro")}>
                <option value="">Tipo registro…</option>
                {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <Input placeholder="Bufete" value={form.bufete} onChange={set("bufete")} className="min-w-36 flex-1" />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Input placeholder="#Solicitud" value={form.solicitud} onChange={set("solicitud")} className="min-w-32 flex-1" />
              <Input placeholder="F. Solicitud" value={form.fecha_solicitud} onChange={set("fecha_solicitud")} className="min-w-32 flex-1" />
              <Input placeholder="#Registro" value={form.registro} onChange={set("registro")} className="min-w-32 flex-1" />
              <Input placeholder="F. Registro" value={form.fecha_registro} onChange={set("fecha_registro")} className="min-w-32 flex-1" />
              <Input placeholder="F. Vencimiento" value={form.fecha_vencimiento} onChange={set("fecha_vencimiento")} className="min-w-32 flex-1" />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Input placeholder="Expediente" value={form.expediente} onChange={set("expediente")} className="min-w-32 flex-1" />
              <Input placeholder="Titular" value={form.titular} onChange={set("titular")} className="min-w-40 flex-1" />
              <Input placeholder="Tramitante" value={form.tramitante} onChange={set("tramitante")} className="min-w-40 flex-1" />
              <Input placeholder="Empresa licenciada" value={form.empresa_licenciada} onChange={set("empresa_licenciada")} className="min-w-44 flex-1" />
            </div>
            <div className="flex flex-wrap gap-2">
              <textarea
                placeholder="Productos/Servicios"
                value={form.productos_servicios}
                onChange={set("productos_servicios")}
                className="min-w-64 flex-1 rounded-md border border-input bg-background p-3 text-sm"
              />
              <textarea
                placeholder="Comentarios"
                value={form.comentarios}
                onChange={set("comentarios")}
                className="min-w-64 flex-1 rounded-md border border-input bg-background p-3 text-sm"
              />
            </div>
            {selected && (
              <div className="flex items-center gap-2">
                {form.etiqueta && <img src={`${API_BASE}${form.etiqueta}`} alt="etiqueta" className="h-12 w-12 rounded border object-cover" />}
                <Input type="file" accept="image/png,image/jpeg" onChange={(e) => setEtiquetaFile(e.target.files?.[0] ?? null)} />
              </div>
            )}
            <div className="flex gap-2">
              <Button type="submit">{selected ? "Guardar" : "Añadir"}</Button>
              {selected && (
                <Button type="button" variant="outline" onClick={() => setHistory(history ? null : [])}>
                  {history ? "Ocultar historial" : "Ver historial"}
                </Button>
              )}
            </div>
            {message && <div className="text-sm text-green-600">{message}</div>}
            <p className="text-xs text-gray-500">
              El matcher exige <b>#Registro</b> (si existe) o <b>#Solicitud</b> como identidad, más el nombre de marca como filtro.
              Si defines ambos, #Registro tiene prioridad.
            </p>
          </form>

          {history && history.length > 0 && (
            <div className="mt-4 space-y-2 border-t pt-3">
              <h4 className="text-sm font-semibold">Historial</h4>
              {history.map((h) => (
                <div key={h.id} className="rounded border p-2 text-sm">
                  <div className="flex justify-between">
                    <Badge variant="outline">{h.estado ?? "—"}</Badge>
                    <span className="text-xs text-gray-500">
                      {h.boletin_period ?? "—"} · {new Date(h.created_at).toLocaleString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {history && history.length === 0 && (
            <div className="mt-4 border-t pt-3 text-sm text-gray-500">Sin historial aún.</div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Marcas</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table className="whitespace-nowrap">
              <TableHeader>
                <TableRow>
                  <TableHead>Marca</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Bufete</TableHead>
                  <TableHead>#Solicitud</TableHead>
                  <TableHead>F. Solicitud</TableHead>
                  <TableHead>#Registro</TableHead>
                  <TableHead>F. Registro</TableHead>
                  <TableHead>F. Vencimiento</TableHead>
                  <TableHead>Clase</TableHead>
                  <TableHead>Titular</TableHead>
                  <TableHead>Tramitante</TableHead>
                  <TableHead>Empresa</TableHead>
                  <TableHead>Productos/Servicios</TableHead>
                  <TableHead>Comentarios</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((p) => (
                  <TableRow key={p.id} className="cursor-pointer" onClick={() => openDetail(p)}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        {p.etiqueta && (
                          <img src={`${API_BASE}${p.etiqueta}`} alt="" className="h-8 w-8 rounded object-cover" />
                        )}
                        {p.name}
                      </div>
                    </TableCell>
                    <TableCell>{p.status ?? "—"}</TableCell>
                    <TableCell>{p.tipo_registro ?? "—"}</TableCell>
                    <TableCell>{p.bufete ?? "—"}</TableCell>
                    <TableCell>{p.solicitud ?? "—"}</TableCell>
                    <TableCell>{p.fecha_solicitud ?? "—"}</TableCell>
                    <TableCell>{p.registro ?? "—"}</TableCell>
                    <TableCell>{p.fecha_registro ?? "—"}</TableCell>
                    <TableCell>{p.fecha_vencimiento ?? "—"}</TableCell>
                    <TableCell>{p.class_nice ?? "—"}</TableCell>
                    <TableCell>{p.titular ?? "—"}</TableCell>
                    <TableCell>{p.tramitante ?? "—"}</TableCell>
                    <TableCell>{p.empresa_licenciada ?? "—"}</TableCell>
                    <TableCell className="max-w-48 truncate">{p.productos_servicios ?? "—"}</TableCell>
                    <TableCell className="max-w-48 truncate">{p.comentarios ?? "—"}</TableCell>
                  </TableRow>
                ))}
                {items.length === 0 && (
                  <TableRow><TableCell colSpan={15} className="text-center text-gray-500">Sin marcas</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

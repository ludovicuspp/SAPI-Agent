import { useCallback, useEffect, useState } from "react";
import { request } from "@/lib/api";
import {
  alertEstadoColor,
  alertEstadoLabel,
  alertCountdown,
  formatDate,
  lapseKeyLabel,
  disposicionLabel,
} from "@/lib/format";
import { useAuthStore } from "@/store/auth";
import { cn } from "@/lib/utils";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { Alert, AlertEstado, LapseConfig } from "@/types/api";

type EstadoFilter = "all" | AlertEstado;

const STATE_FILTERS: { value: EstadoFilter; label: string }[] = [
  { value: "all", label: "Todas" },
  { value: "pendiente", label: "Pendientes" },
  { value: "vencida", label: "Vencidas" },
  { value: "cumplida", label: "Cumplidas" },
  { value: "descartada", label: "Descartadas" },
];

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [filter, setFilter] = useState<EstadoFilter>("all");
  const role = useAuthStore((s) => s.user?.role);

  const loadAlerts = useCallback(() => {
    request<Alert[]>("/api/alerts?limit=1000")
      .then(setAlerts)
      .catch(console.error);
  }, []);

  useEffect(() => {
    loadAlerts();
    const refresh = window.setInterval(loadAlerts, 10_000);
    return () => window.clearInterval(refresh);
  }, [loadAlerts]);

  const visible = alerts.filter((a) => filter === "all" || a.estado === filter);
  const counts = (f: EstadoFilter) =>
    f === "all" ? alerts.length : alerts.filter((a) => a.estado === f).length;

  const resolve = (a: Alert, estado: "cumplida" | "descartada") => {
    request<Alert>(`/api/alerts/${a.id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ estado }),
    })
      .then(() => loadAlerts())
      .catch(console.error);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Lapsos legales</h1>
        <p className="text-sm text-gray-500">
          Plazos de oposición y recursos contados desde la publicación del boletín en días hábiles.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {STATE_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={cn(
              "rounded-full px-3 py-1 text-sm font-medium",
              filter === f.value
                ? "bg-brand-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200",
            )}
          >
            {f.label} ({counts(f.value)})
          </button>
        ))}
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Estado</TableHead>
            <TableHead>Lapso</TableHead>
            <TableHead>Marca</TableHead>
            <TableHead>Expediente</TableHead>
            <TableHead>Boletín</TableHead>
            <TableHead>Publicación</TableHead>
            <TableHead>Límite</TableHead>
            <TableHead>Restan</TableHead>
            <TableHead className="text-right">Acción</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visible.map((a) => (
            <TableRow key={a.id}>
              <TableCell>
                <Badge className={alertEstadoColor(a.estado)}>
                  {alertEstadoLabel(a.estado)}
                </Badge>
              </TableCell>
              <TableCell>
                <div className="font-medium">{lapseKeyLabel(a.lapse_key)}</div>
                {a.tipo_disposicion && (
                  <div className="text-xs text-gray-500">
                    {disposicionLabel(a.tipo_disposicion)}
                  </div>
                )}
              </TableCell>
              <TableCell className="font-medium">{a.marca}</TableCell>
              <TableCell className="font-mono text-xs">{a.expediente ?? "—"}</TableCell>
              <TableCell className="text-sm">{a.boletin_number ?? "—"}</TableCell>
              <TableCell>{formatDate(a.fecha_publicacion)}</TableCell>
              <TableCell>
                <span className={a.estado === "vencida" ? "text-red-600 font-medium" : ""}>
                  {formatDate(a.fecha_limite)}
                </span>
              </TableCell>
              <TableCell>
                <span className={cn(a.estado === "vencida" && "text-red-600 font-medium")}>
                  {alertCountdown(a.dias_restantes)}
                </span>
              </TableCell>
              <TableCell className="text-right">
                {(a.estado === "pendiente" || a.estado === "vencida") && (
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={() => resolve(a, "descartada")}>
                      Descartar
                    </Button>
                    <Button size="sm" onClick={() => resolve(a, "cumplida")}>
                      Cumplida
                    </Button>
                  </div>
                )}
              </TableCell>
            </TableRow>
          ))}
          {visible.length === 0 && (
            <TableRow>
              <TableCell colSpan={9} className="text-center text-gray-500">
                No hay alertas de lapso
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {role === "admin" && <LapseConfigEditor onSaved={loadAlerts} />}
    </div>
  );
}

function LapseConfigEditor({ onSaved }: { onSaved: () => void }) {
  const [configs, setConfigs] = useState<LapseConfig[]>([]);
  const [values, setValues] = useState<Record<string, number>>({});
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    request<LapseConfig[]>("/api/alerts/config")
      .then((rows) => {
        setConfigs(rows);
        setValues(Object.fromEntries(rows.map((c) => [c.key, c.dias_habiles])));
      })
      .catch(console.error);
  }, []);

  const save = (c: LapseConfig) => {
    setSaving(c.key);
    request<LapseConfig>(`/api/alerts/config/${c.key}`, {
      method: "PUT",
      body: JSON.stringify({ dias_habiles: values[c.key] }),
    })
      .then(() => onSaved())
      .catch(console.error)
      .finally(() => setSaving(null));
  };

  return (
    <div className="rounded-md border bg-white p-4">
      <h2 className="mb-3 text-lg font-semibold">Plazos por defecto (días hábiles)</h2>
      <p className="mb-3 text-sm text-gray-500">
        Al cambiar un plazo se recalculan las alertas pendientes de todos los boletines; las ya
        cumplidas o descartadas se conservan.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {configs.map((c) => (
          <div key={c.key} className="flex items-center gap-3 rounded-md border p-3">
            <div className="flex-1">
              <div className="text-sm font-medium">{c.label}</div>
              <div className="text-xs text-gray-500">Por defecto: {c.default_dias_habiles}d</div>
            </div>
            <Input
              type="number"
              min={1}
              value={values[c.key] ?? ""}
              onChange={(e) =>
                setValues((v) => ({ ...v, [c.key]: Number(e.target.value) }))
              }
              className="w-24 text-center"
              aria-label={`Días hábiles ${c.label}`}
            />
            <Button
              size="sm"
              disabled={saving === c.key || (values[c.key] ?? 0) < 1}
              onClick={() => save(c)}
            >
              {saving === c.key ? "Guardando…" : "Guardar"}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
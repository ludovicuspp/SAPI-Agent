import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Activity, AlertTriangle, Database, FileText, GitBranch,
  Layers, Search, Timer, Users, Zap,
} from "lucide-react";

interface Metrics {
  users: number;
  users_active: number;
  boletines_total: number;
  boletines_por_status: Record<string, number>;
  detections_total: number;
  watchlist_total: number;
  portfolio_total: number;
  hermes_queue: number;
  hermes_processed_total: number;
  error_rates: Record<string, { ok: number; error: number; total: number; error_rate_pct: number }>;
  latency_ms: Record<string, { count: number; p50_ms: number; p95_ms: number; max_ms: number }>;
  detections_by_source: Record<string, number>;
  detections_by_confidence: Record<string, number>;
  detections_by_match_kind: Record<string, number>;
  ultimas_24h: { boletines: number; detections: number; scans_ok: number; scans_error: number };
  detections_por_boletin: { min: number; max: number; avg: number };
}

export default function MonitoringPage() {
  const [data, setData] = useState<Metrics | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    request<Metrics>("/api/admin/metrics")
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="text-red-600">Error: {err}</div>;
  if (!data) return <div className="text-gray-500">Cargando…</div>;

  const kpis = [
    { label: "Usuarios activos", value: `${data.users_active}/${data.users}`, icon: Users, color: "text-blue-600" },
    { label: "Boletines", value: data.boletines_total, icon: FileText, color: "text-brand-600" },
    { label: "Cola Hermes", value: data.hermes_queue, icon: GitBranch, color: "text-amber-600" },
    { label: "Detecciones", value: data.detections_total, icon: Search, color: "text-orange-600" },
    { label: "Watchlist", value: data.watchlist_total, icon: Layers, color: "text-indigo-600" },
    { label: "Portfolio", value: data.portfolio_total, icon: Database, color: "text-purple-600" },
  ];

  const stages = ["upload", "extract", "hermes", "notify", "match"];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <Activity className="h-6 w-6" />
        Monitoreo
      </h1>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        {kpis.map((k) => (
          <Card key={k.label} className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-gray-500">{k.label}</div>
                <div className="text-2xl font-bold">{k.value}</div>
              </div>
              <k.icon className={`h-8 w-8 ${k.color}`} />
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <Timer className="h-5 w-5" />
            Latencia por etapa (ms)
          </h2>
          {Object.keys(data.latency_ms).length === 0 ? (
            <div className="text-sm text-gray-500">Sin datos aún.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-gray-500">
                <tr><th className="py-1">Etapa</th><th>p50</th><th>p95</th><th>máx</th><th>n</th></tr>
              </thead>
              <tbody>
                {Object.entries(data.latency_ms).map(([k, v]) => (
                  <tr key={k} className="border-t">
                    <td className="py-1">{k}</td>
                    <td>{v.p50_ms}</td>
                    <td>{v.p95_ms}</td>
                    <td>{v.max_ms}</td>
                    <td className="text-gray-500">{v.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Tasa de error por etapa
          </h2>
          {Object.keys(data.error_rates).length === 0 ? (
            <div className="text-sm text-gray-500">Sin datos aún.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-gray-500">
                <tr><th className="py-1">Etapa</th><th>OK</th><th>Error</th><th>% error</th></tr>
              </thead>
              <tbody>
                {stages.map((s) => {
                  const er = data.error_rates[s];
                  if (!er) return (
                    <tr key={s} className="border-t text-gray-400">
                      <td className="py-1">{s}</td><td>—</td><td>—</td><td>—</td>
                    </tr>
                  );
                  const isHigh = er.error_rate_pct > 10;
                  return (
                    <tr key={s} className="border-t">
                      <td className="py-1">{s}</td>
                      <td>{er.ok}</td>
                      <td>{er.error}</td>
                      <td>
                        <Badge variant={isHigh ? "destructive" : "secondary"}>
                          {er.error_rate_pct}%
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4">
          <h2 className="font-semibold mb-3">Detecciones por fuente</h2>
          {Object.keys(data.detections_by_source).length === 0 ? (
            <div className="text-sm text-gray-500">Sin datos.</div>
          ) : (
            <ul className="text-sm space-y-1">
              {Object.entries(data.detections_by_source).map(([k, v]) => (
                <li key={k} className="flex justify-between">
                  <span>{k}</span><span className="font-mono">{v}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="font-semibold mb-3">Confianza</h2>
          {Object.keys(data.detections_by_confidence).length === 0 ? (
            <div className="text-sm text-gray-500">Sin datos.</div>
          ) : (
            <ul className="text-sm space-y-1">
              {Object.entries(data.detections_by_confidence).map(([k, v]) => (
                <li key={k} className="flex justify-between">
                  <span>{k}</span><span className="font-mono">{v}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="font-semibold mb-3">Últimas 24 h</h2>
          <ul className="text-sm space-y-1">
            <li className="flex justify-between">
              <span>Boletines subidos</span>
              <span className="font-mono">{data.ultimas_24h.boletines}</span>
            </li>
            <li className="flex justify-between">
              <span>Detecciones creadas</span>
              <span className="font-mono">{data.ultimas_24h.detections}</span>
            </li>
            <li className="flex justify-between">
              <span>Scans OK</span>
              <span className="font-mono">{data.ultimas_24h.scans_ok}</span>
            </li>
            <li className="flex justify-between">
              <span>Scans error</span>
              <span className="font-mono text-red-600">{data.ultimas_24h.scans_error}</span>
            </li>
          </ul>
        </Card>
      </div>

      <Card className="p-4 flex items-center justify-between text-sm text-gray-500">
        <span className="flex items-center gap-2">
          <Zap className="h-4 w-4" />
          Datos por boletín: mín {data.detections_por_boletin.min} · máx {data.detections_por_boletin.max} · prom {data.detections_por_boletin.avg}
        </span>
        <span>Estado del boletín: {Object.entries(data.boletines_por_status).map(([k, v]) => `${k}=${v}`).join(", ") || "—"}</span>
      </Card>
    </div>
  );
}
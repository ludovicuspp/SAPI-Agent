import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "@/lib/api";
import { formatSimilarity, statusLabel, statusColor, sourceLabel, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Summary } from "@/types/api";
import { FileText, Search, ListChecks, Briefcase, BellRing } from "lucide-react";

export default function SummaryPage() {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);

    setLoading(true);
    setError(null);
    request<Summary>("/api/summary", { signal: controller.signal })
      .then(setData)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") {
          setError("El resumen tardó demasiado en responder. Intenta de nuevo.");
        } else if (reason instanceof Error) {
          setError(reason.message || "No se pudo cargar el resumen.");
        } else {
          setError("No se pudo cargar el resumen.");
        }
        console.error("No se pudo cargar /api/summary", reason);
      })
      .finally(() => {
        window.clearTimeout(timeout);
        setLoading(false);
      });

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  if (loading) return <div className="text-gray-500">Cargando…</div>;

  if (error || !data) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-bold">Resumen</h1>
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-4 text-red-700">
          <p>{error ?? "No se pudo cargar el resumen."}</p>
          <button
            type="button"
            className="mt-3 rounded-md bg-red-700 px-3 py-2 text-sm font-medium text-white hover:bg-red-800"
            onClick={() => window.location.reload()}
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  const kpis = [
    { label: "Watchlist", value: data.watchlist_count, icon: ListChecks, color: "text-blue-600" },
    { label: "Portfolio", value: data.portfolio_count, icon: Briefcase, color: "text-purple-600" },
    { label: "Boletines", value: data.boletines_count, icon: FileText, color: "text-brand-600" },
    { label: "Detecciones", value: data.detections_count, icon: Search, color: "text-orange-600" },
  ];

  const alertLabel =
    data.alerts_overdue > 0
      ? `Lapsos (${data.alerts_pending} pend. · ${data.alerts_overdue} venc.)`
      : `Lapsos (${data.alerts_pending} pendientes)`;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Resumen</h1>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {kpis.map((kpi) => (
          <Card key={kpi.label} className="flex items-center gap-4 p-4">
            <kpi.icon className={`h-8 w-8 ${kpi.color}`} />
            <div>
              <div className="text-2xl font-bold">{kpi.value}</div>
              <div className="text-sm text-gray-500">{kpi.label}</div>
            </div>
          </Card>
        ))}
        <Link
          to="/lapsos"
          className={cn(
            "flex items-center gap-4 rounded-xl border bg-white p-4 transition-colors hover:bg-gray-50",
            (data.alerts_overdue ?? 0) > 0 && "border-red-200 bg-red-50/50",
          )}
        >
          <BellRing className={cn("h-8 w-8", (data.alerts_overdue ?? 0) > 0 ? "text-red-600" : "text-brand-600")} />
          <div>
            <div className="text-sm font-bold">{alertLabel}</div>
            <div className="text-sm text-gray-500">
              {data.alert_next_due ? `Próximo: ${formatDate(data.alert_next_due)}` : "Sin lapsos activos"}
            </div>
          </div>
        </Link>
      </div>

      {data.recent_boletines.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Últimos boletines</h2>
          <div className="space-y-2">
            {data.recent_boletines.map((b) => (
              <Link
                key={b.id}
                to={`/boletines/${b.id}`}
                className="flex items-center justify-between rounded-md border bg-white p-3 text-sm hover:bg-gray-50"
              >
                <span className="font-medium">{b.filename}</span>
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${statusColor(b.status)}`}>
                  {statusLabel(b.status)}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {data.recent_detections.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Últimas detecciones</h2>
          <div className="space-y-2">
            {data.recent_detections.map((d) => (
              <div key={d.id} className="flex items-center justify-between rounded-md border bg-white p-3 text-sm">
                <div>
                  <span className="font-medium">{d.mark_name}</span>
                  {d.titular && <span className="ml-2 text-gray-500">— {d.titular}</span>}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{formatSimilarity(d.similarity)}</Badge>
                  <Badge>{sourceLabel(d.source)}</Badge>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

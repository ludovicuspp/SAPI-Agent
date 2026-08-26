import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "@/lib/api";
import { formatSimilarity, statusLabel, statusColor, sourceLabel } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Summary } from "@/types/api";
import { FileText, Search, ListChecks, Briefcase } from "lucide-react";

export default function SummaryPage() {
  const [data, setData] = useState<Summary | null>(null);

  useEffect(() => {
    request<Summary>("/api/summary").then(setData).catch(console.error);
  }, []);

  if (!data) return <div className="text-gray-500">Cargando…</div>;

  const kpis = [
    { label: "Watchlist", value: data.watchlist_count, icon: ListChecks, color: "text-blue-600" },
    { label: "Portfolio", value: data.portfolio_count, icon: Briefcase, color: "text-purple-600" },
    { label: "Boletines", value: data.boletines_count, icon: FileText, color: "text-brand-600" },
    { label: "Detecciones", value: data.detections_count, icon: Search, color: "text-orange-600" },
  ];

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

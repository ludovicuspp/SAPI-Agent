import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { formatSimilarity, sourceLabel, formatDate, formatClass, disposicionLabel, disposicionColor } from "@/lib/format";
import { ExportButtons } from "@/components/ExportButtons";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { Detection, MatchKind } from "@/types/api";

type KindFilter = "all" | MatchKind;
type SortMode = "recent" | "risk";

const KIND_LABEL: Record<MatchKind, string> = {
  conflict: "Conflicto",
  similar: "Similar",
  own_status: "Estado propio",
};

const KIND_BADGE: Record<MatchKind, "destructive" | "default" | "secondary"> = {
  conflict: "destructive",
  similar: "default",
  own_status: "secondary",
};

function riskPct(d: Detection): string {
  if (d.risk_score == null) return "—";
  return `${Math.round(d.risk_score * 100)}%`;
}

export default function Detections() {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [selected, setSelected] = useState<Detection | null>(null);
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [sortMode, setSortMode] = useState<SortMode>("risk");

  useEffect(() => {
    let active = true;
    const loadDetections = () => {
      request<Detection[]>("/api/detections?limit=1000")
        .then((items) => {
          if (active) setDetections(items);
        })
        .catch(console.error);
    };

    loadDetections();
    const refresh = window.setInterval(loadDetections, 5000);
    return () => {
      active = false;
      window.clearInterval(refresh);
    };
  }, []);

  const visible = detections
    .filter((d) => kindFilter === "all" || d.match_kind === kindFilter)
    .sort((a, b) => {
      if (sortMode === "recent") {
        return b.detected_at.localeCompare(a.detected_at);
      }
      const ra = a.risk_score ?? 0;
      const rb = b.risk_score ?? 0;
      if (rb !== ra) return rb - ra;
      return b.detected_at.localeCompare(a.detected_at);
    });

  const counts = (kind: KindFilter) =>
    kind === "all"
      ? detections.length
      : detections.filter((d) => d.match_kind === kind).length;

  const originLabel = (d: Detection) => {
    if (d.portfolio_id !== null) {
      return d.match_kind === "own_status" ? "Portfolio · identidad" : "Portfolio · conflicto";
    }
    if (d.watchlist_id !== null && d.match_kind === "conflict") return "Watchlist · titular";
    return "Watchlist";
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Detecciones</h1>
        <ExportButtons dataset="detections" />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {(["all", "conflict", "similar", "own_status"] as KindFilter[]).map((k) => (
          <button
            key={k}
            onClick={() => setKindFilter(k)}
            className={`rounded-full px-3 py-1 text-sm font-medium ${
              kindFilter === k ? "bg-brand-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            {k === "all" ? "Todas" : KIND_LABEL[k as MatchKind]} ({counts(k)})
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 text-sm">
          <label className="text-gray-600">Ordenar:</label>
          <select
            value={sortMode}
            onChange={(e) => setSortMode(e.target.value as SortMode)}
            className="rounded border border-input bg-white px-2 py-1"
          >
            <option value="risk">Por riesgo</option>
            <option value="recent">Más recientes</option>
          </select>
        </div>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Severidad</TableHead>
            <TableHead>Marca</TableHead>
            <TableHead>Match con</TableHead>
            <TableHead>Titular</TableHead>
            <TableHead>Clase</TableHead>
            <TableHead>Riesgo</TableHead>
            <TableHead>Origen</TableHead>
            <TableHead>Fuente</TableHead>
            <TableHead>Fecha</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visible.map((d) => (
            <TableRow
              key={d.id}
              className="cursor-pointer"
              onClick={() => setSelected(d)}
            >
              <TableCell>
                <Badge variant={KIND_BADGE[d.match_kind]}>
                  {KIND_LABEL[d.match_kind]}
                </Badge>
              </TableCell>
              <TableCell className="font-medium">{d.mark_name}</TableCell>
              <TableCell>{d.matched_with ?? "—"}</TableCell>
              <TableCell>{d.titular ?? "—"}</TableCell>
              <TableCell>{formatClass(d.class_nice)}</TableCell>
              <TableCell className={d.risk_score != null && d.risk_score >= 0.7 ? "text-red-600 font-semibold" : ""}>
                {riskPct(d)}
              </TableCell>
              <TableCell>
                <Badge variant={d.portfolio_id !== null ? "default" : "outline"}>
                  {originLabel(d)}
                </Badge>
              </TableCell>
              <TableCell><Badge variant="secondary">{sourceLabel(d.source)}</Badge></TableCell>
              <TableCell>{formatDate(d.detected_at)}</TableCell>
            </TableRow>
          ))}
          {visible.length === 0 && (
            <TableRow>
              <TableCell colSpan={9} className="text-center text-gray-500">
                No hay detecciones
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setSelected(null)}>
          <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold">{selected.mark_name}</h2>
              <Badge variant={KIND_BADGE[selected.match_kind]}>{KIND_LABEL[selected.match_kind]}</Badge>
            </div>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-gray-500">Marca:</dt><dd>{selected.mark_name}</dd>
              <dt className="text-gray-500">Match con:</dt><dd>{selected.matched_with ?? "—"}</dd>
              <dt className="text-gray-500">Titular:</dt><dd>{selected.titular ?? "—"}</dd>
              <dt className="text-gray-500">Expediente:</dt><dd>{selected.expediente ?? "—"}</dd>
              <dt className="text-gray-500">Clase Niza:</dt><dd>{formatClass(selected.class_nice)}</dd>
              <dt className="text-gray-500">Similitud:</dt><dd>{formatSimilarity(selected.similarity)}</dd>
              <dt className="text-gray-500">Riesgo:</dt><dd>{riskPct(selected)}</dd>
              <dt className="text-gray-500">Página:</dt><dd>{selected.page ?? "—"}</dd>
              <dt className="text-gray-500">Origen:</dt><dd>{originLabel(selected)}</dd>
              <dt className="text-gray-500">Match:</dt><dd>{selected.match_kind}</dd>
            </dl>
            {selected.tipo_disposicion && (
              <div className="mt-4">
                <div className="flex items-center gap-2">
                  <div className="text-sm text-gray-500">Disposición administrativa</div>
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${disposicionColor(selected.tipo_disposicion)}`}>
                    {disposicionLabel(selected.tipo_disposicion)}
                  </span>
                </div>
                {selected.disposicion && (
                  <p className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">
                    {selected.disposicion}
                  </p>
                )}
              </div>
            )}
            {selected.raw_excerpt && (
              <pre className="mt-4 max-h-40 overflow-auto rounded bg-gray-50 p-3 text-xs text-gray-700">
                {selected.raw_excerpt}
              </pre>
            )}
            <button onClick={() => setSelected(null)} className="mt-4 text-sm text-brand-600 hover:underline">Cerrar</button>
          </div>
        </div>
      )}
    </div>
  );
}

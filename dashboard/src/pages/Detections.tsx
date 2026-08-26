import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { formatSimilarity, sourceLabel, formatDate, formatClass } from "@/lib/format";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { Detection } from "@/types/api";

export default function Detections() {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [selected, setSelected] = useState<Detection | null>(null);

  useEffect(() => {
    request<Detection[]>("/api/detections?limit=200").then(setDetections).catch(console.error);
  }, []);

  const simColor = (s: number) => (s >= 90 ? "text-red-600 font-bold" : s >= 75 ? "text-orange-600" : "text-gray-600");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Detecciones</h1>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Marca</TableHead>
            <TableHead>Titular</TableHead>
            <TableHead>Clase</TableHead>
            <TableHead>Similitud</TableHead>
            <TableHead>Fuente</TableHead>
            <TableHead>Fecha</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {detections.map((d) => (
            <TableRow
              key={d.id}
              className="cursor-pointer"
              onClick={() => setSelected(d)}
            >
              <TableCell className="font-medium">{d.mark_name}</TableCell>
              <TableCell>{d.titular ?? "—"}</TableCell>
              <TableCell>{formatClass(d.class_nice)}</TableCell>
              <TableCell className={simColor(d.similarity)}>{formatSimilarity(d.similarity)}</TableCell>
              <TableCell><Badge variant="secondary">{sourceLabel(d.source)}</Badge></TableCell>
              <TableCell>{formatDate(d.detected_at)}</TableCell>
            </TableRow>
          ))}
          {detections.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-gray-500">
                No hay detecciones
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setSelected(null)}>
          <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-4 text-lg font-bold">{selected.mark_name}</h2>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-gray-500">Titular:</dt><dd>{selected.titular ?? "—"}</dd>
              <dt className="text-gray-500">Expediente:</dt><dd>{selected.expediente ?? "—"}</dd>
              <dt className="text-gray-500">Clase Niza:</dt><dd>{formatClass(selected.class_nice)}</dd>
              <dt className="text-gray-500">Similitud:</dt><dd>{formatSimilarity(selected.similarity)}</dd>
              <dt className="text-gray-500">Página:</dt><dd>{selected.page ?? "—"}</dd>
              <dt className="text-gray-500">Match:</dt><dd>{selected.match_kind}</dd>
            </dl>
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

import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { request } from "@/lib/api";
import { watchBoletinProgress } from "@/lib/ws";
import { statusLabel, statusColor } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { Boletin, BoletinProgress } from "@/types/api";

export default function BoletinDetail() {
  const { id } = useParams<{ id: string }>();
  const [boletin, setBoletin] = useState<Boletin | null>(null);
  const [progress, setProgress] = useState<BoletinProgress | null>(null);

  useEffect(() => {
    if (!id) return;
    request<Boletin>(`/api/boletines/${id}`).then(setBoletin).catch(console.error);
  }, [id]);

  useEffect(() => {
    if (!boletin || boletin.status !== "extracting") return;
    const unsub = watchBoletinProgress(boletin.id, (e) => {
      setProgress(e);
      if (e.status !== "extracting") {
        // refresh boletin data
        request<Boletin>(`/api/boletines/${id}`).then(setBoletin).catch(console.error);
      }
    });
    return unsub;
  }, [boletin?.status, id]);

  if (!boletin) return <div className="text-gray-500">Cargando…</div>;

  const isExtracting = boletin.status === "extracting" || progress?.status === "extracting";
  const displayStatus = progress?.status ?? boletin.status;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/boletines" className="text-sm text-gray-500 hover:underline">← Boletines</Link>
        <h1 className="text-2xl font-bold">{boletin.filename}</h1>
      </div>

      {isExtracting && (
        <Card>
          <CardContent className="p-6">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="font-medium">Extrayendo texto del PDF…</span>
              {progress?.pages && <span className="text-gray-500">{progress.pages} páginas</span>}
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
              <div className="h-full animate-pulse rounded-full bg-brand-500" style={{ width: "60%" }} />
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card className="p-4">
          <div className="text-sm text-gray-500">Status</div>
          <div className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${statusColor(displayStatus)}`}>
            {statusLabel(displayStatus)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-500">Páginas</div>
          <div className="mt-1 text-xl font-bold">{progress?.pages ?? boletin.pages ?? "…"}</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-500">Entries matcheables</div>
          <div className="mt-1 text-xl font-bold">{progress?.entries_matcheables ?? boletin.entries_matcheables}</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-500">Figura / Lema</div>
          <div className="mt-1 text-xl font-bold">
            {progress?.entries_figura ?? boletin.entries_figura} / {progress?.entries_lema ?? boletin.entries_lema}
          </div>
        </Card>
      </div>

      {boletin.error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-700">{boletin.error}</div>
      )}

      {boletin.status === "extracted" && (
        <Link to={`/detections?boletin_id=${boletin.id}`}>
          <Button>Ver detecciones de este boletín</Button>
        </Link>
      )}
    </div>
  );
}

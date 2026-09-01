import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { request } from "@/lib/api";
import { watchBoletinProgress } from "@/lib/ws";
import { statusLabel, statusColor, stepLabel, isHermesInProgress } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { Boletin, BoletinProgress } from "@/types/api";

export default function BoletinDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
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

  // Poll Hermes: cuando extracted y needs_hermes_review, refrescar cada 3 s
  // para detectar cuando Hermes termina.
  useEffect(() => {
    if (!boletin) return;
    const hermesActive =
      boletin.status === "extracted" &&
      boletin.needs_hermes_review &&
      !boletin.hermes_processed_at;
    if (!hermesActive) return;
    const t = window.setInterval(() => {
      request<Boletin>(`/api/boletines/${id}`).then(setBoletin).catch(console.error);
    }, 3000);
    return () => window.clearInterval(t);
  }, [boletin, id]);

  if (!boletin) return <div className="text-gray-500">Cargando…</div>;

  const isExtracting = boletin.status === "extracting" || progress?.status === "extracting";
  const displayStatus = progress?.status ?? boletin.status;

  const currentStep = progress?.progress_step ?? boletin.progress_step ?? null;
  const currentPage = progress?.progress_current_page ?? boletin.progress_current_page ?? null;
  const totalPages = progress?.progress_total_pages ?? boletin.progress_total_pages ?? null;
  const pctPages =
    progress?.progress_total_pages && progress?.progress_current_page != null
      ? Math.min(100, Math.round((progress.progress_current_page / progress.progress_total_pages) * 100))
      : boletin.progress_total_pages && boletin.progress_current_page != null
      ? Math.min(100, Math.round((boletin.progress_current_page / boletin.progress_total_pages) * 100))
      : null;

  const hermesActive = isHermesInProgress(boletin);

  const handleDelete = async () => {
    if (!window.confirm(
      `¿Eliminar el boletín "${boletin.filename}" y todas sus detecciones? Esta acción no se puede deshacer.`,
    )) return;
    try {
      await request<void>(`/api/boletines/${boletin.id}`, { method: "DELETE" });
      navigate("/boletines");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Error al eliminar");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/boletines" className="text-sm text-gray-500 hover:underline">← Boletines</Link>
        <h1 className="text-2xl font-bold">{boletin.filename}</h1>
      </div>

      {isExtracting && (
        <Card>
          <CardContent className="p-6 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{stepLabel(currentStep) || "Iniciando…"}</span>
              {currentPage != null && totalPages != null && (
                <span className="text-gray-500">
                  Página {currentPage} / {totalPages}
                </span>
              )}
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
              <div
                className="h-full rounded-full bg-brand-500 transition-[width] duration-200"
                style={{ width: pctPages != null ? `${pctPages}%` : "10%" }}
                data-testid="extract-progress-bar"
              />
            </div>
            {pctPages != null && (
              <div className="text-xs text-gray-500">{pctPages}% completado</div>
            )}
          </CardContent>
        </Card>
      )}

      {hermesActive && (
        <Card className="border-purple-200 bg-purple-50">
          <CardContent className="p-6 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-purple-800">
                Analizando por Hermes Vision
              </span>
              <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-purple-500" />
            </div>
            <p className="text-xs text-purple-700">
              El boletín tiene páginas con imágenes o encoding roto.
              La cola de Hermes las está procesando con visión multimodal.
              Esta vista se actualiza automáticamente.
            </p>
            {boletin.entries_hermes_pending > 0 && (
              <p className="text-xs text-purple-700">
                {boletin.entries_hermes_pending} entradas pendientes de revisión visual.
              </p>
            )}
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

      {!isExtracting && !hermesActive && (
        <div className="border-t pt-6">
          <Button variant="destructive" onClick={handleDelete}>
            Eliminar boletín
          </Button>
          <p className="mt-2 text-xs text-gray-500">
            Se borra el registro, sus detecciones y el PDF si ningún otro boletín lo usa.
          </p>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { request } from "@/lib/api";
import {
  formatDate,
  formatClass,
  lapseKeyLabel,
  disposicionLabel,
  alertEstadoLabel,
  alertEstadoColor,
  alertCountdown,
  estadoExpedienteLabel,
  estadoExpedienteColor,
} from "@/lib/format";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Expediente, ExpedienteHito } from "@/types/api";

export default function Expediente() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Expediente | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    request<Expediente>(`/api/portfolio/${id}/expediente`)
      .then(setData)
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Error al cargar expediente");
        console.error(e);
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="text-gray-500">Cargando expediente…</div>;
  if (error || !data) return <div role="alert" className="text-red-600">{error ?? "Error"}</div>;

  const fechaDe = (h: ExpedienteHito) => h.fecha_publicacion ?? "—";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Expediente</h1>
          {data.expedientes.length > 0 && (
            <div className="text-sm text-gray-500">
              Nº expediente: {data.expedientes.join(", ")}
            </div>
          )}
          {data.marcadas.length > 1 && (
            <div className="text-xs text-gray-400">
              Marcas observadas: {data.marcadas.join(" / ")}
            </div>
          )}
        </div>
        <Badge className={estadoExpedienteColor(data.estado)}>
          {estadoExpedienteLabel(data.estado)}
        </Badge>
      </div>

      {data.alerts.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Próximos plazos</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.alerts.map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-md border p-3">
                <div>
                  <span className="font-medium">{lapseKeyLabel(a.lapse_key)}</span>
                  {a.tipo_disposicion && (
                    <span className="ml-2 text-xs text-gray-500">{disposicionLabel(a.tipo_disposicion)}</span>
                  )}
                  <div className="text-xs text-gray-500">
                    Vence: {formatDate(a.fecha_limite)} · {alertCountdown(a.dias_restantes)}
                  </div>
                </div>
                <Badge className={alertEstadoColor(a.estado)}>{alertEstadoLabel(a.estado)}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Línea de tiempo ({data.hitos.length} apariciones)</CardTitle>
        </CardHeader>
        <CardContent>
          {data.hitos.length === 0 && (
            <div className="text-sm text-gray-500">Sin apariciones en boletines procesados.</div>
          )}
          <div className="relative ml-3 border-l-2 border-gray-200 space-y-6 pl-6">
            {data.hitos.map((h) => (
              <div key={h.entry_id} className="relative">
                <div className="absolute -left-8 top-1 h-3 w-3 rounded-full border-2 border-white bg-gray-400" />
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium text-sm">{fechaDe(h)}</span>
                  <span className="text-xs text-gray-500">BPI {h.boletin_number ?? "—"}</span>
                  {h.estatus && <Badge variant="outline" className="text-xs">{h.estatus}</Badge>}
                  {h.tipo_disposicion && <Badge className="text-xs">{disposicionLabel(h.tipo_disposicion)}</Badge>}
                  {h.class_nice != null && <span className="text-xs text-gray-500">Clase {formatClass(h.class_nice)}</span>}
                  {h.page && <span className="text-xs text-gray-400">pág. {h.page}</span>}
                </div>
                {h.disposicion && (
                  <p className="mt-1 max-h-28 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-700">
                    {h.disposicion}
                  </p>
                )}
                <div className="mt-1 text-xs text-gray-400">
                  {h.tramitante ? `Tramitante: ${h.tramitante}` : ""}
                  {h.titular ? ` · Titular: ${h.titular}` : ""}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
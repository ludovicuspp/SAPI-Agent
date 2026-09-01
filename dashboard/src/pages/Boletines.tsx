import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { request } from "@/lib/api";
import { formatDate, statusLabel, statusColor, isHermesInProgress } from "@/lib/format";
import { UploadZone } from "@/components/UploadZone";
import { Button } from "@/components/ui/button";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import type { Boletin } from "@/types/api";

export default function Boletines() {
  const [boletines, setBoletines] = useState<Boletin[]>([]);
  const navigate = useNavigate();

  const load = () => request<Boletin[]>("/api/boletines").then(setBoletines).catch(console.error);

  useEffect(() => { load(); }, []);

  const handleDelete = async (b: Boletin) => {
    if (!window.confirm(
      `¿Eliminar el boletín "${b.filename}" y todas sus detecciones? Esta acción no se puede deshacer.`,
    )) return;
    try {
      await request<void>(`/api/boletines/${b.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Error al eliminar");
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Boletines</h1>
      <UploadZone onUploaded={(id) => navigate(`/boletines/${id}`)} />
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Archivo</TableHead>
            <TableHead>No.</TableHead>
            <TableHead>Páginas</TableHead>
            <TableHead>Entries</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Fecha</TableHead>
            <TableHead className="w-24"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {boletines.map((b) => {
            const extracting = b.status === "extracting";
            const hermesActive = isHermesInProgress(b);
            const locked = extracting || hermesActive;
            return (
              <TableRow key={b.id}>
                <TableCell>
                  <Link to={`/boletines/${b.id}`} className="font-medium text-brand-600 hover:underline">
                    {b.filename}
                  </Link>
                  {hermesActive && (
                    <span
                      className="ml-2 inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-semibold text-purple-700"
                      title="Esperando revisión con Hermes Vision"
                    >
                      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-purple-500" />
                      Hermes Vision
                    </span>
                  )}
                </TableCell>
                <TableCell>{b.bulletin_number ?? "—"}</TableCell>
                <TableCell>{b.pages ?? "…"}</TableCell>
                <TableCell>{b.entries_matcheables}</TableCell>
                <TableCell>
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${statusColor(b.status)}`}>
                    {statusLabel(b.status)}
                  </span>
                </TableCell>
                <TableCell>{formatDate(b.uploaded_at)}</TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={locked}
                    onClick={() => handleDelete(b)}
                    title={
                      extracting
                        ? "El boletín se está extrayendo"
                        : hermesActive
                        ? "Esperando a Hermes Vision"
                        : "Eliminar boletín"
                    }
                  >
                    Eliminar
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
          {boletines.length === 0 && (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-gray-500">
                No hay boletines
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

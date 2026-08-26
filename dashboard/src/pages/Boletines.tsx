import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "@/lib/api";
import { formatDate, statusLabel, statusColor } from "@/lib/format";
import { UploadZone } from "@/components/UploadZone";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import type { Boletin } from "@/types/api";

export default function Boletines() {
  const [boletines, setBoletines] = useState<Boletin[]>([]);

  const load = () => request<Boletin[]>("/api/boletines").then(setBoletines).catch(console.error);

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Boletines</h1>
      <UploadZone onUploaded={() => load()} />
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Archivo</TableHead>
            <TableHead>No.</TableHead>
            <TableHead>Páginas</TableHead>
            <TableHead>Entries</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Fecha</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {boletines.map((b) => (
            <TableRow key={b.id}>
              <TableCell>
                <Link to={`/boletines/${b.id}`} className="font-medium text-brand-600 hover:underline">
                  {b.filename}
                </Link>
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
            </TableRow>
          ))}
          {boletines.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-gray-500">
                No hay boletines
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { Watchlist, WatchlistKind } from "@/types/api";

export default function WatchlistPage() {
  const [items, setItems] = useState<Watchlist[]>([]);
  const [name, setName] = useState("");
  const [cls, setCls] = useState("");
  const [notes, setNotes] = useState("");
  const [productos, setProductos] = useState("");
  const [kind, setKind] = useState<WatchlistKind>("marca");
  const [matchFamily, setMatchFamily] = useState(false);

  const load = () => request<Watchlist[]>("/api/watchlist").then(setItems).catch(console.error);
  useEffect(() => { load(); }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await request<Watchlist>("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({
        name: name.trim(),
        class_nice: cls ? Number(cls) : null,
        notes: notes || null,
        productos_servicios: productos.trim() || null,
        match_family: matchFamily,
        kind,
      }),
    });
    setName(""); setCls(""); setNotes(""); setProductos(""); setMatchFamily(false);
    load();
  };

  const remove = async (id: number) => {
    await request(`/api/watchlist/${id}`, { method: "DELETE" });
    load();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Watchlist</h1>

      <form onSubmit={add} className="flex flex-wrap gap-2">
        <Input placeholder="Nombre de marca" value={name} onChange={(e) => setName(e.target.value)} className="w-48" required />
        <Input placeholder="Clase Niza" type="number" value={cls} onChange={(e) => setCls(e.target.value)} className="w-24" min="1" max="45" />
        <Input placeholder="Productos / servicios (distingue)" value={productos} onChange={(e) => setProductos(e.target.value)} className="flex-1 min-w-64" maxLength={2000} />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as WatchlistKind)}
          className="rounded border border-input bg-white px-2 py-1"
          title="Marca: vigila una marca registrada. Titular: vigila un nombre de titular/competidor en las solicitudes."
        >
          <option value="marca">Marca</option>
          <option value="titular">Titular</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={matchFamily} onChange={(e) => setMatchFamily(e.target.checked)} />
          Familia
        </label>
        <Input placeholder="Notas" value={notes} onChange={(e) => setNotes(e.target.value)} className="w-48" />
        <Button type="submit">Añadir</Button>
      </form>

      <p className="text-xs text-gray-500">
        El matcher exige nombre (fuzzy) + clase Niza + distingue (intersección de tokens).
        Activa <strong>Familia</strong> para detectar derivados (DRAGON ← DRAGON WINCH) y usa
        <strong> Titular</strong> para vigilar un nombre de titular/competidor.
      </p>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Marca</TableHead>
            <TableHead>Tipo</TableHead>
            <TableHead>Clase</TableHead>
            <TableHead>Productos / servicios</TableHead>
            <TableHead>Familia</TableHead>
            <TableHead>Notas</TableHead>
            <TableHead>Acciones</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((w) => (
            <TableRow key={w.id}>
              <TableCell className="font-medium">{w.name}</TableCell>
              <TableCell>
                <Badge variant={w.kind === "titular" ? "destructive" : "default"}>
                  {w.kind === "titular" ? "Titular" : "Marca"}
                </Badge>
              </TableCell>
              <TableCell>{w.class_nice ?? "—"}</TableCell>
              <TableCell className="max-w-md truncate" title={w.productos_servicios ?? ""}>
                {w.productos_servicios ?? "—"}
              </TableCell>
              <TableCell>{w.match_family ? "Sí" : "—"}</TableCell>
              <TableCell>{w.notes ?? "—"}</TableCell>
              <TableCell>
                <Button variant="ghost" size="sm" onClick={() => remove(w.id)}>
                  Desactivar
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {items.length === 0 && (
            <TableRow><TableCell colSpan={7} className="text-center text-gray-500">Sin entradas</TableCell></TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

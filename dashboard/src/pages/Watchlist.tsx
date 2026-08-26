import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Watchlist } from "@/types/api";

export default function WatchlistPage() {
  const [items, setItems] = useState<Watchlist[]>([]);
  const [name, setName] = useState("");
  const [cls, setCls] = useState("");
  const [notes, setNotes] = useState("");

  const load = () => request<Watchlist[]>("/api/watchlist").then(setItems).catch(console.error);
  useEffect(() => { load(); }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await request<Watchlist>("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({ name: name.trim(), class_nice: cls ? Number(cls) : null, notes: notes || null }),
    });
    setName(""); setCls(""); setNotes("");
    load();
  };

  const remove = async (id: number) => {
    await request(`/api/watchlist/${id}`, { method: "DELETE" });
    load();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Watchlist</h1>

      <form onSubmit={add} className="flex gap-2">
        <Input placeholder="Nombre de marca" value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
        <Input placeholder="Clase" value={cls} onChange={(e) => setCls(e.target.value)} className="w-20" />
        <Input placeholder="Notas" value={notes} onChange={(e) => setNotes(e.target.value)} className="flex-1" />
        <Button type="submit">Añadir</Button>
      </form>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Marca</TableHead>
            <TableHead>Clase</TableHead>
            <TableHead>Notas</TableHead>
            <TableHead>Acciones</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((w) => (
            <TableRow key={w.id}>
              <TableCell className="font-medium">{w.name}</TableCell>
              <TableCell>{w.class_nice ?? "—"}</TableCell>
              <TableCell>{w.notes ?? "—"}</TableCell>
              <TableCell>
                <Button variant="ghost" size="sm" onClick={() => remove(w.id)}>
                  Desactivar
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {items.length === 0 && (
            <TableRow><TableCell colSpan={4} className="text-center text-gray-500">Sin entradas</TableCell></TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

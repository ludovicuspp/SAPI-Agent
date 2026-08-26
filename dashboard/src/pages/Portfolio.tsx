import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Portfolio } from "@/types/api";

export default function PortfolioPage() {
  const [items, setItems] = useState<Portfolio[]>([]);
  const [name, setName] = useState("");
  const [exp, setExp] = useState("");
  const [cls, setCls] = useState("");

  const load = () => request<Portfolio[]>("/api/portfolio").then(setItems).catch(console.error);
  useEffect(() => { load(); }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await request<Portfolio>("/api/portfolio", {
      method: "POST",
      body: JSON.stringify({
        name: name.trim(),
        expediente: exp || null,
        class_nice: cls ? Number(cls) : null,
      }),
    });
    setName(""); setExp(""); setCls("");
    load();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Portfolio</h1>

      <form onSubmit={add} className="flex gap-2">
        <Input placeholder="Nombre" value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
        <Input placeholder="Expediente" value={exp} onChange={(e) => setExp(e.target.value)} className="w-36" />
        <Input placeholder="Clase" value={cls} onChange={(e) => setCls(e.target.value)} className="w-20" />
        <Button type="submit">Añadir</Button>
      </form>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nombre</TableHead>
            <TableHead>Expediente</TableHead>
            <TableHead>Clase</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((p) => (
            <TableRow key={p.id}>
              <TableCell className="font-medium">{p.name}</TableCell>
              <TableCell>{p.expediente ?? "—"}</TableCell>
              <TableCell>{p.class_nice ?? "—"}</TableCell>
              <TableCell>{p.status ?? "Pendiente"}</TableCell>
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

import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { User } from "@/types/api";

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "agent">("agent");
  const [error, setError] = useState("");

  const load = () => request<User[]>("/api/users").then(setUsers).catch(console.error);
  useEffect(() => { load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await request<User>("/api/users", {
        method: "POST",
        body: JSON.stringify({ email, password, role }),
      });
      setEmail(""); setPassword(""); setRole("agent");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    }
  };

  const deactivate = async (id: number) => {
    await request(`/api/users/${id}`, { method: "DELETE" });
    load();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Usuarios</h1>

      <form onSubmit={create} className="flex gap-2">
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required className="flex h-10 rounded-md border px-3 text-sm" />
        <input type="password" placeholder="Contraseña (8+)" value={password} onChange={(e) => setPassword(e.target.value)} required className="flex h-10 w-40 rounded-md border px-3 text-sm" />
        <select value={role} onChange={(e) => setRole(e.target.value as "admin" | "agent")} className="h-10 rounded-md border px-3 text-sm">
          <option value="agent">Agent</option>
          <option value="admin">Admin</option>
        </select>
        <Button type="submit">Crear</Button>
      </form>
      {error && <div className="text-sm text-red-600">{error}</div>}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead>Rol</TableHead>
            <TableHead>Activo</TableHead>
            <TableHead>Acciones</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((u) => (
            <TableRow key={u.id}>
              <TableCell className="font-medium">{u.email}</TableCell>
              <TableCell><Badge variant={u.role === "admin" ? "default" : "secondary"}>{u.role}</Badge></TableCell>
              <TableCell>{u.active ? "Sí" : "No"}</TableCell>
              <TableCell>
                {u.active && (
                  <Button variant="ghost" size="sm" onClick={() => deactivate(u.id)}>
                    Desactivar
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

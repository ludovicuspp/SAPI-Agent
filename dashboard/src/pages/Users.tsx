import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { User, UserRole } from "@/types/api";

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [email, setEmail] = useState("");
  const [nombre, setNombre] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("empresa");
  const [error, setError] = useState("");

  const load = () => request<User[]>("/api/users").then(setUsers).catch(console.error);
  useEffect(() => { load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await request<User>("/api/users", {
        method: "POST",
        body: JSON.stringify({ email, nombre, password, role }),
      });
      setEmail(""); setNombre(""); setPassword(""); setRole("empresa");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    }
  };

  const removeUser = async (id: number) => {
    if (!window.confirm("¿Eliminar este usuario? Se borrarán sus marcas y portafolio.")) return;
    await request(`/api/users/${id}`, { method: "DELETE" });
    load();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Usuarios</h1>

      <form onSubmit={create} className="flex flex-wrap gap-2">
        <input type="text" placeholder="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} required className="flex h-10 rounded-md border px-3 text-sm" />
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required className="flex h-10 rounded-md border px-3 text-sm" />
        <input type="password" placeholder="Contraseña (8+)" value={password} onChange={(e) => setPassword(e.target.value)} required className="flex h-10 w-44 rounded-md border px-3 text-sm" />
        <select value={role} onChange={(e) => setRole(e.target.value as UserRole)} className="h-10 rounded-md border px-3 text-sm">
          <option value="empresa">Empresa</option>
          <option value="propietario">Propietario</option>
          <option value="admin">Admin</option>
        </select>
        <Button type="submit">Crear</Button>
      </form>
      {error && <div className="text-sm text-red-600">{error}</div>}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nombre</TableHead>
            <TableHead>Email</TableHead>
            <TableHead>Rol</TableHead>
            <TableHead>Acciones</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((u) => (
            <TableRow key={u.id}>
              <TableCell className="font-medium">{u.nombre || u.email}</TableCell>
              <TableCell>{u.email}</TableCell>
              <TableCell><Badge variant={u.role === "admin" ? "default" : "secondary"}>{u.role}</Badge></TableCell>
              <TableCell>
                <Button variant="ghost" size="sm" className="text-red-600" onClick={() => removeUser(u.id)}>
                  Eliminar
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

import { NavLink, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  FileText,
  Search,
  ListChecks,
  Briefcase,
  Users,
  LogOut,
} from "lucide-react";

const navItems = [
  { to: "/", label: "Resumen", icon: LayoutDashboard },
  { to: "/boletines", label: "Boletines", icon: FileText },
  { to: "/detections", label: "Detecciones", icon: Search },
  { to: "/watchlist", label: "Watchlist", icon: ListChecks },
  { to: "/portfolio", label: "Portfolio", icon: Briefcase },
];

export default function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  return (
    <div className="flex h-screen">
      <aside className="flex w-60 flex-col border-r bg-white">
        <div className="flex h-14 items-center border-b px-4 font-bold text-brand-700">
          SAPI-Agent
        </div>
        <nav className="flex-1 space-y-1 p-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-gray-600 hover:bg-gray-100",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
          {user?.role === "admin" && (
            <NavLink
              to="/users"
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-gray-600 hover:bg-gray-100",
                )
              }
            >
              <Users className="h-4 w-4" />
              Usuarios
            </NavLink>
          )}
        </nav>
        <div className="border-t p-4">
          <div className="mb-2 truncate text-xs text-gray-500">{user?.email ?? "—"}</div>
          <button
            onClick={logout}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-gray-600 hover:bg-gray-100"
          >
            <LogOut className="h-4 w-4" />
            Cerrar sesión
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}

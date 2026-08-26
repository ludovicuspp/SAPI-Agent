import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user || user.role !== "admin") return <Navigate to="/" replace />;
  return <>{children}</>;
}

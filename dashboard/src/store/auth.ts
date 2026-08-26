import { create } from "zustand";
import { request, setToken, clearToken } from "@/lib/api";
import type { User } from "@/types/api";

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  loadFromStorage: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem("sapi-token"),
  loading: false,

  login: async (email, password) => {
    set({ loading: true });
    try {
      const { access_token } = await request<{ access_token: string; expires_in: number }>(
        "/api/auth/login",
        { method: "POST", body: JSON.stringify({ email, password }) },
      );
      setToken(access_token);
      // Decode user from JWT payload (no network call needed)
      const payload = JSON.parse(atob(access_token.split(".")[1] ?? "")) as Record<string, unknown>;
      set({ token: access_token, user: { id: Number(payload.sub ?? 0), email, role: (payload.role as "admin" | "agent") ?? "agent", active: true, created_at: "" } });
    } finally {
      set({ loading: false });
    }
  },

  logout: () => {
    clearToken();
    set({ token: null, user: null });
  },

  loadFromStorage: () => {
    const token = localStorage.getItem("sapi-token");
    if (!token) return;
    try {
      const payload = JSON.parse(atob(token.split(".")[1] ?? "")) as Record<string, unknown>;
      if (typeof payload.exp === "number" && payload.exp * 1000 < Date.now()) {
        clearToken();
        return;
      }
      set({ token, user: { id: Number(payload.sub ?? 0), email: String(payload.email ?? ""), role: (payload.role as "admin" | "agent") ?? "agent", active: true, created_at: "" } });
    } catch {
      clearToken();
    }
  },
}));

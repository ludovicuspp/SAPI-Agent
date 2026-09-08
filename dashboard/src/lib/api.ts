const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export function getToken(): string | null {
  return localStorage.getItem("sapi-token");
}

export function setToken(token: string): void {
  localStorage.setItem("sapi-token", token);
}

export function clearToken(): void {
  localStorage.removeItem("sapi-token");
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

class ApiError extends Error {
  constructor(
    public status: number,
    detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new ApiError(401, "No autorizado");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    let detail = body.detail;
    // FastAPI devuelve los 422 como array de {loc, msg, type}; normalizar
    // a texto legible en lugar de dejar un objeto (que se renderiza "[object Object]").
    if (Array.isArray(detail)) {
      detail = detail.map((d) => d.msg ?? String(d)).join("; ");
    } else if (typeof detail !== "string") {
      detail = JSON.stringify(detail);
    }
    throw new ApiError(res.status, detail || "Error desconocido");
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function uploadFile<T>(
  path: string,
  file: File,
): Promise<T> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new ApiError(401, "No autorizado");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || "Error desconocido");
  }
  return res.json();
}

export function wsBase(): string {
  const configured = import.meta.env.VITE_WS_BASE_URL;
  if (configured) return configured;
  // Mismo origen (producción): resuelve el protocolo/host actual de la
  // página (wss: si es https, ws: si es http) para evitar fijar dominio.
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

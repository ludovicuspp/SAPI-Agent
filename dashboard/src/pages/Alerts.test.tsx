import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Alerts from "./Alerts";

let mockRole = "admin";
let mockAlerts: unknown[] = [];
let mockConfigs: unknown[] = [];

const mockRequest = vi.fn(
  (path: string, options?: { method?: string; body?: string }) => {
    if (path === "/api/alerts/config") return Promise.resolve(mockConfigs);
    if (path.startsWith("/api/alerts/config/") && options?.method === "PUT") {
      return Promise.resolve({ ...JSON.parse(options.body ?? "{}"), key: path.split("/").pop() });
    }
    if (path.startsWith("/api/alerts/") && options?.method === "POST") {
      return Promise.resolve({ estado: "cumplida", resolved_at: "2026-09-09T09:00:00" });
    }
    return Promise.resolve(mockAlerts);
  },
);

vi.mock("@/lib/api", () => ({
  request: (...args: unknown[]) =>
    mockRequest(args[0] as string, args[1] as { method?: string; body?: string }),
}));

vi.mock("@/store/auth", () => ({
  useAuthStore: (sel: (s: unknown) => unknown) =>
    sel({ user: { role: mockRole, email: "a@s" } }),
}));

function alertOver(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    user_id: 1,
    detection_id: 10,
    boletin_id: 2,
    store: null,
    lapse_key: "pago_concesion",
    estado: "pendiente",
    dias_habiles: 30,
    dias_restantes: 12,
    fecha_publicacion: "2026-09-01",
    fecha_limite: "2026-10-13",
    resolved_at: null,
    created_at: "2026-09-09T00:00:00",
    marca: "MARCA X",
    expediente: "2026-004444",
    boletin_number: 654,
    period: "2026-06",
    disposicion: null,
    tipo_disposicion: "CONCESION",
    ...over,
  };
}

const CONFIG = [
  { key: "pago_concesion", label: "Pago de concesión", dias_habiles: 30, default_dias_habiles: 30 },
  { key: "oposicion", label: "Oposición a publicación", dias_habiles: 30, default_dias_habiles: 30 },
];

beforeEach(() => {
  mockRequest.mockClear();
  mockRole = "admin";
  mockAlerts = [alertOver()];
  mockConfigs = CONFIG;
});

describe("Alerts page", () => {
  it("shows alert rows with filters", async () => {
    mockAlerts = [
      alertOver(),
      alertOver({ id: 2, estado: "vencida", dias_restantes: -4 }),
    ];
    render(
      <MemoryRouter>
        <Alerts />
      </MemoryRouter>,
    );
    expect(await screen.findAllByText("MARCA X")).toHaveLength(2);
    expect(screen.getAllByText("Pago de concesión").length).toBeGreaterThan(0);
    expect(screen.getByText("Vencida")).toBeDefined();
  });

  it("resolves an alert as cumplida", async () => {
    render(
      <MemoryRouter>
        <Alerts />
      </MemoryRouter>,
    );
    const btn = await screen.findByRole("button", { name: "Cumplida" });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(mockRequest).toHaveBeenCalledWith(
        "/api/alerts/1/resolve",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ estado: "cumplida" }),
        }),
      );
    });
  });

  it("renders the admin config editor and saves a new plazo", async () => {
    render(
      <MemoryRouter>
        <Alerts />
      </MemoryRouter>,
    );

    const input = (await screen.findAllByLabelText(/Días hábiles/))[0]!;
    await waitFor(() => expect(input).not.toHaveValue(null));
    fireEvent.change(input, { target: { value: "15" } });
    const guardar = screen.getAllByRole("button", { name: "Guardar" })[0]!;
    fireEvent.click(guardar);

    await waitFor(() => {
      expect(mockRequest).toHaveBeenCalledWith(
        "/api/alerts/config/pago_concesion",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({ dias_habiles: 15 }),
        }),
      );
    });
  });

  it("hides the config editor for non-admins", async () => {
    mockRole = "empresa";
    render(
      <MemoryRouter>
        <Alerts />
      </MemoryRouter>,
    );
    await screen.findByText("MARCA X");
    expect(screen.queryByText("Plazos por defecto (días hábiles)")).toBeNull();
    expect(mockRequest).not.toHaveBeenCalledWith("/api/alerts/config", expect.anything());
  });
});
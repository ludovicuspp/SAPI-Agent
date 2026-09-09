import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ExportButtons } from "./ExportButtons";
import { setToken } from "@/lib/api";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("ExportButtons", () => {
  it("renderiza los botones CSV y Markdown", () => {
    render(<ExportButtons dataset="detections" />);
    expect(screen.getByText("CSV")).toBeDefined();
    expect(screen.getByText("Markdown")).toBeDefined();
  });

  it("descarga el csv llevando el token de auth", async () => {
    setToken("t-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("col1,col2\n1,2", {
        status: 200,
        headers: { "Content-Type": "text/csv" },
      }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<ExportButtons dataset="detections" />);
    fireEvent.click(screen.getByText("CSV"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    const url = String(fetchMock.mock.calls[0]?.[0]);
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    // El base URL depende del entorno (VITE_API_BASE_URL); validar el path.
    expect(url).toContain("/api/export/detections.csv");
    expect(init.headers).toEqual({
      Authorization: "Bearer t-token",
    });
  });

  it("muestra el mensaje de error si la API falla", async () => {
    setToken("t-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    vi.spyOn(window, "alert").mockImplementation(() => {});

    render(<ExportButtons dataset="watchlist" />);
    fireEvent.click(screen.getByText("Markdown"));

    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith("boom");
    });
  });
});

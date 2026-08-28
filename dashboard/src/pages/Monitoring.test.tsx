import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Monitoring from "@/pages/Monitoring";

vi.mock("@/lib/api", () => ({
  request: vi.fn(),
}));

import { request } from "@/lib/api";
const mockRequest = request as unknown as ReturnType<typeof vi.fn>;

const fakeMetrics = {
  users: 2,
  users_active: 2,
  boletines_total: 3,
  boletines_por_status: { extracted: 2, failed: 1 },
  detections_total: 5,
  watchlist_total: 4,
  portfolio_total: 1,
  hermes_queue: 1,
  hermes_processed_total: 0,
  error_rates: {
    extract: { ok: 2, error: 0, total: 2, error_rate_pct: 0 },
    hermes: { ok: 0, error: 2, total: 2, error_rate_pct: 100 },
  },
  latency_ms: {
    extract: { count: 2, p50_ms: 1200, p95_ms: 3000, max_ms: 3000 },
  },
  detections_by_source: { pdfplumber_text: 3, hermes_vision: 2 },
  detections_by_confidence: { high: 4, medium: 1 },
  detections_by_match_kind: { similar: 5 },
  ultimas_24h: { boletines: 1, detections: 2, scans_ok: 5, scans_error: 1 },
  detections_por_boletin: { min: 1, max: 3, avg: 1.67 },
};

describe("MonitoringPage", () => {
  beforeEach(() => {
    mockRequest.mockReset();
  });

  it("muestra KPIs principales", async () => {
    mockRequest.mockResolvedValueOnce(fakeMetrics);
    render(
      <MemoryRouter>
        <Monitoring />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Monitoreo")).toBeInTheDocument();
    });
    expect(screen.getByText("Cola Hermes")).toBeInTheDocument();
    expect(screen.getByText("Watchlist")).toBeInTheDocument();
    expect(screen.getByText("Portfolio")).toBeInTheDocument();
  });

  it("muestra tabla de latencia por etapa", async () => {
    mockRequest.mockResolvedValueOnce(fakeMetrics);
    render(
      <MemoryRouter>
        <Monitoring />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/Latencia por etapa/)).toBeInTheDocument();
    });
    expect(screen.getAllByText("extract").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1200").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3000").length).toBeGreaterThan(0);
  });

  it("muestra tasa de error con badge destructivo si > 10%", async () => {
    mockRequest.mockResolvedValueOnce(fakeMetrics);
    render(
      <MemoryRouter>
        <Monitoring />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("100%")).toBeInTheDocument();
    });
  });

  it("muestra mensaje de error si la API falla", async () => {
    mockRequest.mockRejectedValueOnce(new Error("403"));
    render(
      <MemoryRouter>
        <Monitoring />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/Error/)).toBeInTheDocument();
    });
  });

  it("muestra empty state cuando no hay métricas", async () => {
    mockRequest.mockResolvedValueOnce({
      ...fakeMetrics,
      latency_ms: {},
      error_rates: {},
      detections_by_source: {},
      detections_by_confidence: {},
    });
    render(
      <MemoryRouter>
        <Monitoring />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getAllByText(/Sin datos/).length).toBeGreaterThan(0);
    });
  });
});
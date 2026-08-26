import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import SummaryPage from "./Summary";

const mockRequest = vi.fn();

vi.mock("@/lib/api", () => ({
  request: (...args: unknown[]) => mockRequest(...args),
}));

beforeEach(() => {
  mockRequest.mockReset();
});

describe("Summary page", () => {
  it("shows loading initially", () => {
    mockRequest.mockReturnValue(new Promise(() => {})); // never resolves
    render(
      <MemoryRouter>
        <SummaryPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Cargando…")).toBeDefined();
  });

  it("renders KPIs after load", async () => {
    mockRequest.mockResolvedValue({
      watchlist_count: 5,
      portfolio_count: 3,
      boletines_count: 12,
      detections_count: 47,
      last_boletin_at: null,
      recent_detections: [],
      recent_boletines: [],
    });
    render(
      <MemoryRouter>
        <SummaryPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("5")).toBeDefined();
    expect(screen.getByText("Watchlist")).toBeDefined();
    expect(screen.getByText("Portfolio")).toBeDefined();
    expect(screen.getByText("Boletines")).toBeDefined();
    expect(screen.getByText("Detecciones")).toBeDefined();
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import WatchlistPage from "./Watchlist";

const mockRequest = vi.fn();

vi.mock("@/lib/api", () => ({
  request: (...args: unknown[]) => mockRequest(...args),
}));

beforeEach(() => {
  mockRequest.mockReset();
  mockRequest.mockResolvedValue([]);
});

describe("Watchlist page", () => {
  it("renders heading", () => {
    render(
      <MemoryRouter>
        <WatchlistPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Watchlist")).toBeDefined();
  });

  it("renders add form", () => {
    render(
      <MemoryRouter>
        <WatchlistPage />
      </MemoryRouter>,
    );
    expect(screen.getByPlaceholderText(/nombre/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /añadir/i })).toBeDefined();
  });

  it("shows empty state", () => {
    render(
      <MemoryRouter>
        <WatchlistPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Sin entradas")).toBeDefined();
  });
});

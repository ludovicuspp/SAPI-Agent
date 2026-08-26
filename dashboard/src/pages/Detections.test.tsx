import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Detections from "./Detections";

const mockRequest = vi.fn();

vi.mock("@/lib/api", () => ({
  request: (...args: unknown[]) => mockRequest(...args),
}));

beforeEach(() => {
  mockRequest.mockReset();
  mockRequest.mockResolvedValue([]);
});

describe("Detections page", () => {
  it("renders heading", () => {
    render(
      <MemoryRouter>
        <Detections />
      </MemoryRouter>,
    );
    expect(screen.getByText("Detecciones")).toBeDefined();
  });

  it("shows empty state", () => {
    render(
      <MemoryRouter>
        <Detections />
      </MemoryRouter>,
    );
    expect(screen.getByText("No hay detecciones")).toBeDefined();
  });
});

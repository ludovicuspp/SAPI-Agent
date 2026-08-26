import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ProtectedRoute } from "./ProtectedRoute";
import { useAuthStore } from "@/store/auth";

function TestChild() {
  return <div>Protected content</div>;
}

describe("ProtectedRoute", () => {
  it("redirects to /login when no token", () => {
    useAuthStore.setState({ token: null });
    render(
      <MemoryRouter initialEntries={["/secret"]}>
        <ProtectedRoute>
          <TestChild />
        </ProtectedRoute>
      </MemoryRouter>,
    );
    expect(screen.queryByText("Protected content")).toBeNull();
  });

  it("renders children when token present", () => {
    useAuthStore.setState({ token: "valid-token" });
    render(
      <MemoryRouter initialEntries={["/secret"]}>
        <ProtectedRoute>
          <TestChild />
        </ProtectedRoute>
      </MemoryRouter>,
    );
    expect(screen.getByText("Protected content")).toBeDefined();
  });
});

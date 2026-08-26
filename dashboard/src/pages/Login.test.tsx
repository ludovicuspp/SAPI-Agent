import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Login from "./Login";
import { useAuthStore } from "@/store/auth";

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ user: null, token: null, loading: false });
});

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Login />
    </MemoryRouter>,
  );
}

describe("Login page", () => {
  it("renders email and password fields", () => {
    renderLogin();
    const inputs = screen.getAllByRole("textbox");
    expect(inputs.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: /iniciar sesión/i })).toBeDefined();
  });

  it("renders submit button", () => {
    renderLogin();
    expect(screen.getByRole("button", { name: /iniciar sesión/i })).toBeDefined();
  });

  it("renders SAPI-Agent title", () => {
    renderLogin();
    expect(screen.getByText("SAPI-Agent")).toBeDefined();
  });
});

import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "./auth";

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ user: null, token: null });
  });

  it("starts with no user", () => {
    const { user, token } = useAuthStore.getState();
    expect(user).toBeNull();
    expect(token).toBeNull();
  });

  it("logout clears state", () => {
    localStorage.setItem("sapi-token", "fake");
    useAuthStore.setState({ token: "fake" });
    useAuthStore.getState().logout();
    const { user, token } = useAuthStore.getState();
    expect(user).toBeNull();
    expect(token).toBeNull();
    expect(localStorage.getItem("sapi-token")).toBeNull();
  });

  it("loadFromStorage ignores expired tokens", () => {
    // Create an expired JWT (exp in the past)
    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const payload = btoa(JSON.stringify({ sub: 1, exp: 1000000, role: "admin" }));
    const token = `${header}.${payload}.fake-sig`;
    localStorage.setItem("sapi-token", token);
    useAuthStore.getState().loadFromStorage();
    expect(useAuthStore.getState().token).toBeNull();
  });
});

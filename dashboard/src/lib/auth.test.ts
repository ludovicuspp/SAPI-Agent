import { describe, it, expect, beforeEach } from "vitest";
import { getToken, setToken, clearToken, isAuthenticated } from "./api";

describe("auth token persistence", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns null when no token", () => {
    expect(getToken()).toBeNull();
    expect(isAuthenticated()).toBe(false);
  });

  it("stores and retrieves token", () => {
    setToken("my-jwt-token");
    expect(getToken()).toBe("my-jwt-token");
    expect(isAuthenticated()).toBe(true);
  });

  it("clears token", () => {
    setToken("my-jwt-token");
    clearToken();
    expect(getToken()).toBeNull();
    expect(isAuthenticated()).toBe(false);
  });
});

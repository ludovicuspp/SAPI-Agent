import { describe, it, expect } from "vitest";
import { formatDate, formatDateTime, formatSimilarity, formatClass, statusLabel, statusColor, sourceLabel } from "@/lib/format";

describe("formatDate", () => {
  it("returns — for null", () => expect(formatDate(null)).toBe("—"));
  it("formats ISO date to es-VE", () => {
    const result = formatDate("2026-03-15T00:00:00");
    expect(result).toContain("2026");
    expect(result).toContain("mar");
  });
});

describe("formatDateTime", () => {
  it("returns — for null", () => expect(formatDateTime(null)).toBe("—"));
  it("formats ISO datetime", () => {
    const result = formatDateTime("2026-03-15T14:30:00");
    expect(result).toContain("2026");
  });
});

describe("formatSimilarity", () => {
  it("rounds to integer percentage", () => {
    expect(formatSimilarity(92.4)).toBe("92%");
    expect(formatSimilarity(92.6)).toBe("93%");
    expect(formatSimilarity(100)).toBe("100%");
  });
});

describe("formatClass", () => {
  it("returns — for null", () => expect(formatClass(null)).toBe("—"));
  it("returns LC for 0", () => expect(formatClass(0)).toBe("LC"));
  it("returns number as string", () => expect(formatClass(25)).toBe("25"));
});

describe("statusLabel", () => {
  it("maps known statuses", () => {
    expect(statusLabel("extracting")).toBe("Extrayendo");
    expect(statusLabel("extracted")).toBe("Extraído");
    expect(statusLabel("failed")).toBe("Error");
  });
  it("returns raw status for unknown", () => {
    expect(statusLabel("custom")).toBe("custom");
  });
});

describe("statusColor", () => {
  it("returns CSS classes for known statuses", () => {
    expect(statusColor("extracted")).toContain("green");
    expect(statusColor("failed")).toContain("red");
    expect(statusColor("extracting")).toContain("blue");
  });
});

describe("sourceLabel", () => {
  it("maps sources to Spanish", () => {
    expect(sourceLabel("pdfplumber_text")).toBe("Parser");
    expect(sourceLabel("hermes_llm")).toBe("Hermes LLM");
    expect(sourceLabel("hermes_vision")).toBe("Hermes Visión");
  });
});

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { UploadZone } from "./UploadZone";

describe("UploadZone", () => {
  it("renders upload prompt", () => {
    render(<UploadZone onUploaded={() => {}} />);
    expect(screen.getByText(/arrastra un pdf/i)).toBeDefined();
  });

  it("has hidden file input for PDF", () => {
    render(<UploadZone onUploaded={() => {}} />);
    const input = screen.getByLabelText(/arrastra un pdf/i).closest("div")?.querySelector("input[type='file']");
    expect(input).toBeDefined();
    expect(input).toHaveAttribute("accept", ".pdf");
  });
});

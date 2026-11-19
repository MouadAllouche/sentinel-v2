import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SeverityBadge } from "@/components/badges/SeverityBadge";
import { strengthLabel } from "@/components/badges/StrengthBadge";

describe("design system", () => {
  it.each(["low", "medium", "high", "critical"] as const)(
    "SeverityBadge renders a text label for %s",
    (severity) => {
      render(<SeverityBadge severity={severity} />);
      expect(screen.getByText(severity, { exact: false })).toBeInTheDocument();
    },
  );

  it("labels link strength textually, not only by colour", () => {
    expect(strengthLabel("weak")).toContain("Weak");
    expect(strengthLabel("strong")).toContain("Strong");
  });
});

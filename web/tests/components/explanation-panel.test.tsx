import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExplanationPanel } from "@/components/incidents/ExplanationPanel";

describe("Why grouped tab", () => {
  it("shows every strong and weak link reason exactly once", () => {
    render(
      <ExplanationPanel
        explanation={{
          grouping: {
            strong: ["Same source IP 203.0.113.45; 2m apart", "Rule evidence: ssh-bruteforce-by-ip"],
            weak: ["Weak: config_drift 4m after sudo_command; time proximity only"],
          },
          anchors: [],
          rules: [],
          caveats: ["Grouping is based on shared attributes and time proximity."],
        }}
      />,
    );
    expect(screen.getByText("Same source IP 203.0.113.45; 2m apart")).toBeInTheDocument();
    expect(screen.getByText("Rule evidence: ssh-bruteforce-by-ip")).toBeInTheDocument();
    // Reasons already carry their own "Weak:" prefix; the UI must not double it.
    expect(
      screen.getByText("Weak: config_drift 4m after sudo_command; time proximity only"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Weak: Weak:/)).not.toBeInTheDocument();
  });
});

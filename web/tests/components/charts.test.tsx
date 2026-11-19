import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BaselineBandChart } from "@/components/charts/BaselineBandChart";

describe("BaselineBandChart", () => {
  it("renders an accessible fallback table with band values", () => {
    render(
      <BaselineBandChart
        series={[
          { timestamp: "2026-11-15T10:00:00+00:00", value: 25, mean: 2, stddev: 1, upper: 5, lower: -1 },
        ]}
        maturity="mature"
      />,
    );
    const table = screen.getByRole("table");
    expect(table).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
  });

  it("never presents an immature baseline as all clear", () => {
    render(<BaselineBandChart series={[]} maturity="immature" reason="only 6 hours of history" />);
    expect(screen.getByText(/not enough data/i)).toBeInTheDocument();
  });
});

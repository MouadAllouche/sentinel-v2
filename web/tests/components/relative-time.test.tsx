import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RelativeTime } from "@/components/badges/RelativeTime";

describe("RelativeTime SSR stability", () => {
  it("renders the absolute UTC instant on the server, independent of the clock", () => {
    const a = renderToString(<RelativeTime value="2026-11-19T10:00:00+00:00" />);
    const b = renderToString(<RelativeTime value="2026-11-19T10:00:00+00:00" />);
    expect(a).toBe(b);
    expect(a).toContain("2026-11-19 10:00:00");
    expect(a).toContain("UTC");
  });
});

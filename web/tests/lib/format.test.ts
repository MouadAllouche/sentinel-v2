import { describe, expect, it } from "vitest";
import { formatRelative, formatScore, formatUtc } from "@/lib/format";

describe("format helpers", () => {
  it("formats a UTC timestamp without changing the instant", () => {
    expect(formatUtc("2026-11-15T10:00:00+00:00")).toContain("2026-11-15");
    expect(formatUtc("2026-11-15T10:00:00+00:00")).toContain("10:00");
  });

  it("formats relative gaps in plain language", () => {
    expect(formatRelative("2026-11-15T10:00:00+00:00", "2026-11-15T10:03:12+00:00")).toBe(
      "3m 12s",
    );
    expect(formatRelative("2026-11-15T10:00:00+00:00", "2026-11-15T10:00:05+00:00")).toBe(
      "5s",
    );
  });

  it("formats scores as integers capped at 100", () => {
    expect(formatScore(45)).toBe("45");
    expect(formatScore(150)).toBe("100");
  });
});

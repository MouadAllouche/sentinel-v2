import { describe, expect, it } from "vitest";
import {
  emptyFilters,
  filtersToSearch,
  formatDelta,
  isValidCidr,
  parseEventFilters,
  rangeForPreset,
} from "@/lib/filters";

describe("event filter URL helpers", () => {
  it("round-trips array filters through the URL", () => {
    const filters = {
      ...emptyFilters,
      event_type: ["failed_login", "sudo_command"],
      severity: ["high", "critical"],
      search: "root",
      allowlisted: true as boolean | null,
      limit: 100,
    };
    const search = filtersToSearch(filters);
    const parsed = parseEventFilters(search);
    expect(parsed.event_type).toEqual(["failed_login", "sudo_command"]);
    expect(parsed.severity).toEqual(["high", "critical"]);
    expect(parsed.search).toBe("root");
    expect(parsed.allowlisted).toBe(true);
    expect(parsed.limit).toBe(100);
  });

  it("validates CIDR input and rejects host addresses and bad octets", () => {
    expect(isValidCidr("203.0.113.0/24")).toBe(true);
    expect(isValidCidr("2001:db8::/32")).toBe(true);
    expect(isValidCidr("203.0.113.45")).toBe(false);
    expect(isValidCidr("999.0.0.0/24")).toBe(false);
    expect(isValidCidr("203.0.113.0/33")).toBe(false);
  });

  it("expands a preset into an absolute range when the URL has no times", () => {
    const parsed = parseEventFilters("?preset=24h", "2026-11-19T12:00:00+00:00");
    expect(parsed.since).toBe("2026-11-18T12:00:00+00:00");
    expect(parsed.until).toBe("2026-11-19T12:00:00+00:00");
  });

  it("round-trips the any-incident toggle", () => {
    const search = filtersToSearch({ ...emptyFilters, in_incident: true });
    expect(parseEventFilters(search).in_incident).toBe(true);
  });

  it("formats deltas with counts and percentages", () => {
    expect(formatDelta(12, 10)).toBe("+2 (+20%)");
    expect(formatDelta(8, 10)).toBe("-2 (-20%)");
    expect(formatDelta(0, 0)).toBe("0 (0%)");
    expect(formatDelta(3, 0)).toBe("new");
  });

  it("resolves time range presets inclusively", () => {
    const now = "2026-11-19T12:00:00+00:00";
    expect(rangeForPreset("24h", now)).toEqual({
      since: "2026-11-18T12:00:00+00:00",
      until: now,
    });
    expect(rangeForPreset("7d", now).since).toBe("2026-11-12T12:00:00+00:00");
    expect(rangeForPreset("30d", now).since).toBe("2026-10-20T12:00:00+00:00");
  });
});

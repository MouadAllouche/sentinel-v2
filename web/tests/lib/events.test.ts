import { describe, expect, it } from "vitest";
import { eventTypeGroup, groupBySeverity, severitySourceText } from "@/lib/events";

describe("event explanation helpers", () => {
  it.each([
    [{ severity_source: "default" }, "default severity"],
    [{ severity_source: "override:12" }, "override 12"],
    [{ severity_source: "rule:ssh-bruteforce" }, "rule ssh-bruteforce"],
    [{}, "fallback"],
  ])("explains the severity source for %j", (event, expected) => {
    expect(severitySourceText(event)).toBe(expected);
  });

  it("groups severities for quick stats", () => {
    expect(
      groupBySeverity([{ severity: "low" }, { severity: "high" }, { severity: "low" }]),
    ).toEqual({ low: 2, high: 1 });
  });

  it("maps event types to filter groups", () => {
    expect(eventTypeGroup("failed_login")).toBe("Authentication");
    expect(eventTypeGroup("port_scan")).toBe("Network");
    expect(eventTypeGroup("unknown_type")).toBe("System");
  });
});

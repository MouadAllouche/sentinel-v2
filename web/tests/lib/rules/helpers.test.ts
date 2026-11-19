import { describe, expect, it } from "vitest";
import {
  definitionForKind,
  describeCondition,
  diffRules,
  mapServerErrors,
  roundTripDefinition,
  ruleSummary,
  secondsToWindow,
  tierSentence,
  validateRegex,
  validateThresholds,
  windowToSeconds,
} from "@/lib/rules/helpers";

describe("rule builder pure helpers", () => {
  it("converts tier windows both ways", () => {
    expect(windowToSeconds(10, "minutes")).toBe(600);
    expect(windowToSeconds(1, "hours")).toBe(3600);
    expect(secondsToWindow(600)).toEqual({ value: 10, unit: "minutes" });
    expect(secondsToWindow(3600)).toEqual({ value: 1, unit: "hours" });
    expect(secondsToWindow(60)).toEqual({ value: 1, unit: "minutes" });
  });

  it("matches the user's example sentence exactly", () => {
    expect(
      tierSentence(
        { count: 5, window_seconds: 600, severity: "medium", points: 0, label: "Low" },
        { event_types: ["failed_login"], group_by: ["source_ip"] },
      ),
    ).toBe("If ≥ 5 failed logins from the same source IP occur within 10 minutes → MEDIUM");
    expect(
      tierSentence(
        { count: 20, window_seconds: 600, severity: "high", points: 30, label: "High" },
        { event_types: ["failed_login"], group_by: ["source_ip"] },
      ),
    ).toContain("(+30 points)");
  });

  it("generates a rule summary sentence", () => {
    const summary = ruleSummary({
      name: "SSH brute force",
      match: { event_types: ["failed_login"] },
      group_by: ["source_ip"],
      tiers: [
        { label: "Medium", points: 5, count: 5, window_seconds: 600, severity: "medium" },
        { label: "High", points: 30, count: 20, window_seconds: 600, severity: "high" },
      ],
    });
    expect(summary).toBe("Failed logins grouped by source IP: ≥5 in 10 min → medium; ≥20 in 10 min → high");
  });

  it("builds baseline z-tiers under the canonical tiers key", () => {
    const definition = definitionForKind("baseline_metric", {
      kind: "threshold",
      tiers: [{ label: "Medium", count: 5, window_seconds: 600, severity: "medium", points: 5 }],
      steps: [],
      correlate_on: [],
      within_seconds: 0,
      field: null,
      per: null,
      learning_days: 30,
      min_history_events: 0,
      metric: null,
      subject: null,
      min_std: 1,
      meta_conditions: [],
    });
    expect(definition.tiers[0]).toMatchObject({ z: 3, min_absolute: 5, severity: "high" });
    expect(definition.metric).toBe("failed_login_count");
  });

  it("round-trips a definition losslessly", () => {
    const definition = {
      id: "example-rule",
      kind: "threshold",
      match: { event_types: ["failed_login"], conditions: { all: [{ field: "username", op: "eq", value: "root" }] } },
      tiers: [{ label: "Low", count: 5, window_seconds: 600, severity: "medium", points: 5 }],
    };
    expect(roundTripDefinition(roundTripDefinition(definition))).toEqual(definition);
  });

  it("describes nested conditions in plain language", () => {
    const text = describeCondition({
      all: [
        { field: "event_type", op: "eq", value: "failed_login" },
        { any: [{ field: "username", op: "eq", value: "root" }, { field: "source_ip", op: "cidr_in", value: "203.0.113.0/24" }] },
      ],
    });
    expect(text).toContain("event_type equals failed_login");
    expect(text).toContain("username equals root");
    expect(text).toContain("source_ip is in 203.0.113.0/24");
    expect(text).toContain("AND");
    expect(text).toContain("OR");
  });

  it("rejects unsafe regex patterns", () => {
    expect(validateRegex("^sshd.*")).toBeNull();
    expect(validateRegex("(a+)+")).toContain("nested");
    expect(validateRegex(".*.*.*.*.*.*Z")).toContain("quantifiers");
    expect(validateRegex("a".repeat(201))).toContain("200");
  });

  it("diffs rules by field path", () => {
    const diffs = diffRules(
      { name: "Old", tiers: [{ count: 5 }] },
      { name: "New", tiers: [{ count: 20 }] },
    );
    expect(diffs).toEqual([
      { path: "name", before: "Old", after: "New" },
      { path: "tiers[0].count", before: 5, after: 20 },
    ]);
  });

  it("maps server paths to form fields", () => {
    const setError = (() => undefined) as (field: string, error: { message: string }) => void;
    expect(() =>
      mapServerErrors(
        [{ path: "tiers[1].count", message: "too small" }, { path: "name", message: "required" }],
        setError,
      ),
    ).not.toThrow();
  });

  it("validates strictly increasing thresholds", () => {
    expect(validateThresholds({ medium: 20, high: 40, critical: 70 })).toBeNull();
    expect(validateThresholds({ medium: 40, high: 20, critical: 70 })).toContain("increasing");
  });
});

import { describe, expect, it } from "vitest";
import {
  auditDiff,
  bandSeries,
  healthHints,
  maturityText,
  passwordStrength,
  retentionIssues,
  validateEnvName,
} from "@/lib/admin/helpers";

describe("admin pure helpers", () => {
  it("zero-fills band series and computes mean ± zσ", () => {
    const rows = bandSeries(
      [
        { timestamp: "2026-11-19T10:00:00+00:00", value: 25 },
        { timestamp: "2026-11-19T12:00:00+00:00", value: 5 },
      ],
      { mean: 10, stddev: 2 },
      [1, 3],
    );
    expect(rows).toHaveLength(3);
    expect(rows[1]?.value).toBe(0);
    expect(rows[0]?.lower1).toBe(8);
    expect(rows[0]?.upper3).toBe(16);
  });

  it("marks anomaly points", () => {
    const rows = bandSeries([{ timestamp: "t1", value: 25 }], { mean: 2, stddev: 1 }, [3], 20);
    expect(rows[0]?.anomaly).toBe(true);
  });

  it("describes maturity without claiming all-clear", () => {
    expect(maturityText(6, 24)).toContain("learning");
    expect(maturityText(24, 24)).toBe("mature");
    expect(maturityText(0, 24)).toContain("Not enough data");
  });

  it("validates secret environment variable names", () => {
    expect(validateEnvName("SENTINEL_WEBHOOK_SECRET")).toBeNull();
    expect(validateEnvName("secret")).toContain("uppercase");
    expect(validateEnvName("SENTINEL-WEBHOOK")).toContain("uppercase");
  });

  it("diffs audit before/after JSON", () => {
    const diff = auditDiff({ a: 1, b: 2 }, { a: 2, c: 3 });
    expect(diff).toEqual([
      { path: "a", kind: "changed", before: 1, after: 2 },
      { path: "b", kind: "removed", before: 2 },
      { path: "c", kind: "added", after: 3 },
    ]);
  });

  it("scores password strength without external libraries", () => {
    expect(passwordStrength("short")).toBe("weak");
    expect(passwordStrength("CorrectHorseBatteryStaple7")).toBe("strong");
  });

  it("validates retention policy ages", () => {
    expect(retentionIssues({ low_days: 30, medium_days: 60, high_days: 90, critical_days: 180 })).toEqual([]);
    expect(retentionIssues({ low_days: 90, medium_days: 30 })[0]).toContain("increasing");
  });

  it("maps known warnings to how-to-fix hints", () => {
    expect(healthHints(["auth.log: permission denied"])[0]).toContain("adm");
    expect(healthHints([])).toEqual([]);
  });
});

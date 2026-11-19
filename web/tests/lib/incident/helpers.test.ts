import { describe, expect, it } from "vitest";
import {
  allowedTransitions,
  collapseRepeats,
  collapseTimelineEntries,
  formatGap,
  layoutGraph,
  sanitizeMarkdown,
  whatIfScore,
} from "@/lib/incident/helpers";

const THRESHOLDS = { medium: 20, high: 40, critical: 70 };

const reasons = [
  { rule_id: "ssh-bruteforce-by-ip", points: 15, severity: "medium" },
  { rule_id: "success-after-failures", points: 20, severity: "high" },
  { rule_id: "sensitive-sudo", points: 20, severity: "high" },
  { rule_id: "world-writable-sensitive-file", points: 40, severity: "critical" },
  { rule_id: "sensitive-file-change", points: 30, severity: "high" },
  { rule_id: "multiple-related-events", points: 10, severity: "medium" },
  { rule_id: "credential-to-privilege-chain", points: 15, severity: "high" },
  { rule_id: "drift-after-access", points: 20, severity: "high" },
];

describe("incident pure helpers", () => {
  it("matches the Phase 10 worked example including the cap", () => {
    const result = whatIfScore(reasons, THRESHOLDS, []);
    expect(result.raw).toBe(170);
    expect(result.score).toBe(100);
    expect(result.capped).toBe(true);
    expect(result.severity).toBe("critical");
  });

  it("recalculates after disabling rules and resolves score-band boundaries", () => {
    const withoutCriticalRule = whatIfScore(reasons, THRESHOLDS, [
      "world-writable-sensitive-file",
    ]);
    expect(withoutCriticalRule.raw).toBe(130);
    expect(withoutCriticalRule.score).toBe(100);
    expect(whatIfScore([], THRESHOLDS, []).severity).toBe("low");
    expect(whatIfScore([{ rule_id: "a", points: 20, severity: "low" }], THRESHOLDS, []).severity).toBe(
      "medium",
    );
    expect(whatIfScore([{ rule_id: "a", points: 70, severity: "low" }], THRESHOLDS, []).severity).toBe(
      "critical",
    );
  });

  it("collapses repeated events without losing the first/last times", () => {
    const events = [
      { id: 1, timestamp: "2026-11-19T10:00:03+00:00", event_type: "failed_login", severity: "low" },
      { id: 2, timestamp: "2026-11-19T10:01:00+00:00", event_type: "failed_login", severity: "low" },
      { id: 3, timestamp: "2026-11-19T10:04:51+00:00", event_type: "sudo_command", severity: "high" },
    ];
    const collapsed = collapseRepeats(events);
    expect(collapsed[0]?.count).toBe(2);
    expect(collapsed[0]?.last).toBe("2026-11-19T10:01:00+00:00");
    expect(collapsed[1]?.count).toBe(1);
  });

  it("collapses timeline repeats while keeping inferred entries", () => {
    const collapsed = collapseTimelineEntries([
      { timestamp: "10:00:03", event_type: "failed_login", severity: "low", summary: "a", event_id: 1 },
      { timestamp: "10:01:00", event_type: "failed_login", severity: "low", summary: "b", event_id: 2 },
      { timestamp: "10:02:00", event_type: "inferred", severity: "medium", kind: "inferred", summary: "possible guessing" },
    ]);
    expect(collapsed[0]?.kind).toBe("group");
    expect(collapsed[0]?.count).toBe(2);
    expect(collapsed[0]?.ids).toEqual([1, 2]);
    expect(collapsed[1]?.kind).toBe("inferred");
  });

  it("formats relative gaps in plain language", () => {
    expect(
      formatGap("2026-11-19T10:00:00+00:00", "2026-11-19T10:03:12+00:00"),
    ).toBe("+3m 12s");
  });

  it("lays out a graph deterministically with unique node ids", () => {
    const nodes = [
      { id: "source_ip:203.0.113.45", kind: "source_ip", value: "203.0.113.45" },
      { id: "username:root", kind: "username", value: "root" },
    ];
    const edges = [
      { a: "source_ip:203.0.113.45", b: "username:root", strength: "strong", reason: "same event" },
    ];
    const a = layoutGraph(nodes, edges);
    const b = layoutGraph([...nodes].reverse(), edges);
    expect(a).toEqual(b);
    expect(new Set(a.nodes.map((node) => node.id)).size).toBe(2);
  });

  it("renders markdown-lite inertly", () => {
    const safe = sanitizeMarkdown("**bold** <script>alert(1)</script> [x](javascript:alert(1))");
    expect(safe).toContain("<strong>bold</strong>");
    expect(safe).not.toContain("<script>");
    expect(safe).not.toContain("javascript:");
  });

  it("only offers allowed status transitions", () => {
    expect(allowedTransitions("open")).toContain("investigating");
    expect(allowedTransitions("resolved")).not.toContain("open");
    expect(allowedTransitions("merged")).toEqual([]);
  });
});

import { describe, expect, it } from "vitest";

import { ruleSchema } from "@/lib/rules/schema";

/** Mirrors RuleBuilder's `blank` defaults for a threshold rule. */
const blankDefinition = {
  id: "e2e-failed-logins-by-ip",
  name: "E2E failed logins by source IP",
  description: "",
  kind: "threshold",
  enabled: true,
  match: { event_types: ["failed_login"], conditions: { all: [] } },
  scope: { exclude_allowlisted: true },
  actions: { create_incident: true, notify: true, tags: [] },
  mitre: [],
  group_by: ["source_ip"],
  aggregate: { type: "count", field: null },
  window_mode: "sliding",
  fixed_alignment: null,
  cooldown_seconds: 0,
  tiers: [{ label: "Medium", count: 5, window_seconds: 600, severity: "medium", points: 5 }],
  z_tiers: [],
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
};

describe("ruleSchema and the form builder defaults", () => {
  it("accepts the null optional fields used by the blank threshold rule", () => {
    const result = ruleSchema.safeParse(blankDefinition);
    expect(result.error?.issues ?? []).toEqual([]);
    expect(result.success).toBe(true);
  });
});

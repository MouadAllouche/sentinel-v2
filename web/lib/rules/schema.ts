import { z } from "zod";

/** Advisory client validation; the server's validator remains authoritative. */
export const ruleSchema = z
  .object({
    id: z
      .string()
      .min(3, "id must be at least 3 characters")
      .max(64, "id must be at most 64 characters")
      .regex(/^[a-z0-9][a-z0-9-]{2,63}$/, "id must be a lowercase slug"),
    name: z.string().min(1, "Name is required"),
    description: z.string(),
    kind: z.string(),
    enabled: z.boolean(),
    match: z
      .object({ event_types: z.array(z.string()), conditions: z.unknown() })
      .passthrough(),
    scope: z.object({ exclude_allowlisted: z.boolean() }).passthrough(),
    actions: z
      .object({
        create_incident: z.boolean(),
        notify: z.boolean(),
        tags: z.array(z.string()),
      })
      .passthrough(),
    mitre: z.array(z.string()),
    group_by: z.array(z.string()),
    aggregate: z.object({ type: z.string() }).passthrough(),
    window_mode: z.string(),
    cooldown_seconds: z.number().min(0),
    tiers: z
      .array(
        z.object({
          label: z.string(),
          severity: z.string(),
          points: z.number().min(0).max(100),
          count: z.number().int().min(1).max(100_000).optional(),
          window_seconds: z.number().int().min(10).max(2_592_000).optional(),
          z: z.number().min(0.5).max(100).optional(),
          min_absolute: z.number().int().min(1).optional(),
        }),
      )
      .max(10, "At most 10 tiers are allowed")
      .optional(),
    z_tiers: z.array(z.record(z.string(), z.unknown())).max(10).optional(),
    metric: z.string().nullish(),
    subject: z.string().nullish(),
    min_std: z.number().min(0.1).optional(),
    meta_conditions: z.array(z.record(z.string(), z.unknown())).max(5).optional(),
    steps: z.array(z.record(z.string(), z.unknown())).max(5).optional(),
    correlate_on: z.array(z.string()).optional(),
    within_seconds: z.number().optional(),
    field: z.string().nullish(),
    per: z.string().nullish(),
    learning_days: z.number().optional(),
    min_history_events: z.number().optional(),
  })
  .passthrough()
  .superRefine((value, context) => {
    if (value.kind === "threshold" && !(value.tiers && value.tiers.length >= 1)) {
      context.addIssue({ code: "custom", path: ["tiers"], message: "At least one tier is required" });
    }
    if (value.kind === "baseline_metric" && !(value.tiers && value.tiers.length >= 1)) {
      context.addIssue({ code: "custom", path: ["tiers"], message: "At least one z-tier is required" });
    }
  });

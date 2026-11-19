"use client";

import { useState } from "react";

import { Button, Input } from "@/components/ui/primitives";
import { retentionIssues } from "@/lib/admin/helpers";
import type { Role } from "@/lib/auth";

const KEYS = ["low_days", "medium_days", "high_days", "critical_days"] as const;

export function RetentionPanel({
  policy,
  onChange,
  dryRun,
  onPreview,
  onApply,
  onSave,
  role,
}: {
  policy: { events: Record<string, number> };
  onChange: (policy: { events: Record<string, number> }) => void;
  dryRun: { pruned?: number } | null;
  onPreview: () => void;
  onApply: () => void;
  onSave: () => void;
  role: Role;
}) {
  const [confirmation, setConfirmation] = useState("");
  const events = policy.events ?? {};
  const issues = retentionIssues(events);
  return (
    <section aria-label="Retention policy" className="space-y-3 rounded border border-slate-200 p-3 dark:border-slate-700">
      <h2 className="font-semibold">Retention</h2>
      {KEYS.map((key) => (
        <label key={key} className="mr-3 text-sm">
          {key}
          <Input
            aria-label={key}
            type="number"
            min={1}
            className="ml-1 w-24"
            value={events[key] ?? 0}
            readOnly={role !== "admin"}
            onChange={(event) =>
              onChange({ ...policy, events: { ...events, [key]: Number(event.target.value) } })
            }
          />
        </label>
      ))}
      {issues.length ? <p role="alert" className="text-sm text-red-700">{issues.join("; ")}</p> : null}
      <div className="flex flex-wrap gap-2">
        <Button disabled={role !== "admin" || issues.length > 0} onClick={onSave}>Save policy</Button>
        <Button disabled={role !== "admin" || issues.length > 0} onClick={onPreview}>Dry run</Button>
      </div>
      {dryRun ? <p role="status" className="text-sm">Would prune {dryRun.pruned ?? 0} rows. Evidence of open incidents and needed baselines is protected.</p> : null}
      {role === "admin" ? (
        <div className="flex flex-wrap items-center gap-2">
          <Input aria-label="Type confirm" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="Type confirm" />
          <Button disabled={issues.length > 0 || confirmation !== "confirm"} onClick={onApply}>Apply</Button>
        </div>
      ) : null}
    </section>
  );
}

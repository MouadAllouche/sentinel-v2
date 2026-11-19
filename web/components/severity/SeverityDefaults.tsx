"use client";

import { Button, Input } from "@/components/ui/primitives";
import type { Role } from "@/lib/auth";

export interface SeverityRow {
  event_type: string;
  severity: string;
  points: number;
  events_24h?: number;
  modified?: boolean;
  enabled?: boolean;
}

const SEVERITIES = ["low", "medium", "high", "critical"];

export function SeverityDefaults({
  rows,
  dirty,
  onSave,
  onResetAll,
  onChange,
  onResetRow,
  currentRole,
}: {
  rows: SeverityRow[];
  dirty: boolean;
  onSave: () => void;
  onResetAll: () => void;
  onChange: (index: number, changes: Partial<SeverityRow>) => void;
  onResetRow: (eventType: string) => void;
  currentRole: Role;
}) {
  const admin = currentRole === "admin";
  return (
    <section aria-label="Event-type defaults" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto font-semibold">Event-type defaults</h2>
        <Button disabled={!dirty || !admin} onClick={onSave}>Save changes</Button>
        <Button disabled={!admin} onClick={onResetAll}>Reset all to defaults</Button>
      </div>
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Default severity per event type</caption>
        <thead>
          <tr>
            <th scope="col">Event type</th><th scope="col">Severity</th><th scope="col">Points</th>
            <th scope="col">Events 24h</th><th scope="col">Enabled</th><th scope="col">Reset</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.event_type} className="border-b border-slate-100 dark:border-slate-800">
              <th scope="row">
                {row.event_type}
                {row.modified ? <span className="ml-2 text-xs text-amber-800">modified</span> : null}
              </th>
              <td>
                <select
                  aria-label={`Severity for ${row.event_type}`}
                  disabled={!admin}
                  className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                  value={row.severity}
                  onChange={(event) => onChange(index, { severity: event.target.value })}
                >
                  {SEVERITIES.map((severity) => <option key={severity} value={severity}>{severity}</option>)}
                </select>
              </td>
              <td>
                <Input
                  aria-label={`Points for ${row.event_type}`}
                  type="number"
                  min={0}
                  max={100}
                  disabled={!admin}
                  value={row.points}
                  onChange={(event) => onChange(index, { points: Number(event.target.value) })}
                />
              </td>
              <td>{row.events_24h ?? 0}</td>
              <td>
                <input
                  type="checkbox"
                  aria-label={`Enable ${row.event_type}`}
                  disabled={!admin}
                  checked={row.enabled !== false}
                  onChange={(event) => onChange(index, { enabled: event.target.checked })}
                />
              </td>
              <td>
                <Button disabled={!admin} onClick={() => onResetRow(row.event_type)}>Reset</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-amber-800 dark:text-amber-200">
        Disabled types are not stored — evidence is lost.
      </p>
    </section>
  );
}

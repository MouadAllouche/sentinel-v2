"use client";

import { Button, Card, Input } from "@/components/ui/primitives";
import { auditDiff } from "@/lib/admin/helpers";
import type { Role } from "@/lib/auth";

export interface AuditRow {
  id: number;
  ts: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  before?: unknown;
  after?: unknown;
  before_json?: string | null;
  after_json?: string | null;
}

export interface AuditFilters {
  actor: string;
  action: string;
  targetType: string;
  since: string;
  until: string;
}

export function AuditPage({
  rows,
  filters,
  onFiltersChange,
  onExport,
  role,
}: {
  rows: AuditRow[];
  filters: AuditFilters;
  onFiltersChange: (filters: AuditFilters) => void;
  onExport: () => void;
  role: Role;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Audit log</h1>
        <Button onClick={onExport} disabled={role !== "admin"}>Export CSV</Button>
      </div>
      <section aria-label="Audit filters" className="flex flex-wrap gap-2 rounded border border-slate-200 p-3 text-sm dark:border-slate-700">
        <Input aria-label="Actor" placeholder="Actor" value={filters.actor} onChange={(event) => onFiltersChange({ ...filters, actor: event.target.value })} />
        <Input aria-label="Action prefix" placeholder="Action" value={filters.action} onChange={(event) => onFiltersChange({ ...filters, action: event.target.value })} />
        <Input aria-label="Target type" placeholder="Target type" value={filters.targetType} onChange={(event) => onFiltersChange({ ...filters, targetType: event.target.value })} />
        <Input aria-label="Since" placeholder="Since" value={filters.since} onChange={(event) => onFiltersChange({ ...filters, since: event.target.value })} />
        <Input aria-label="Until" placeholder="Until" value={filters.until} onChange={(event) => onFiltersChange({ ...filters, until: event.target.value })} />
      </section>
      <Card>
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Audit entries</caption>
          <thead><tr><th scope="col">Time</th><th scope="col">Actor</th><th scope="col">Action</th><th scope="col">Target</th><th scope="col">Change</th></tr></thead>
          <tbody>
            {rows.map((row) => {
              const parse = (text: string | null | undefined) => {
                if (!text) return null;
                try {
                  return JSON.parse(text) as unknown;
                } catch {
                  return text;
                }
              };
              const diff = auditDiff(
                row.before ?? parse(row.before_json),
                row.after ?? parse(row.after_json),
              );
              return (
                <tr key={row.id} className="border-b border-slate-100 align-top dark:border-slate-800">
                  <td>{row.ts}</td><td>{row.actor}</td><td>{row.action}</td>
                  <td>{row.target_type}:{row.target_id}</td>
                  <td>
                    <ul>
                      {diff.map((item, index) => (
                        <li key={index}>
                          {item.path}: {item.kind}{" "}
                          {item.kind === "changed" ? `${JSON.stringify(item.before)} → ${JSON.stringify(item.after)}` : ""}
                        </li>
                      ))}
                    </ul>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

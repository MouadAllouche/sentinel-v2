"use client";

import Link from "next/link";

import { Button, Input } from "@/components/ui/primitives";
import type { Role } from "@/lib/auth";

export interface RuleRow {
  id: string;
  name: string;
  enabled: boolean;
  kind: string;
  summary?: string;
  builtin?: boolean;
  modified?: boolean;
  version?: number;
  last_fired?: string | null;
  findings_24h?: number;
  findings_7d?: number;
  tier_severities?: string[];
}

export interface RulesFilters {
  kind: string;
  enabled: boolean | null;
  search: string;
  builtin: boolean | null;
  noisy: boolean;
}

export function RulesList({
  rules,
  filters,
  onFiltersChange,
  onToggle,
  onDuplicate,
  onReset,
  onDelete,
  onImport,
  onExport,
  currentRole,
}: {
  rules: RuleRow[];
  filters: RulesFilters;
  onFiltersChange: (filters: RulesFilters) => void;
  onToggle: (id: string, enabled: boolean) => void;
  onDuplicate: (id: string) => void;
  onReset: (id: string) => void;
  onDelete: (id: string) => void;
  onImport: () => void;
  onExport: () => void;
  currentRole: Role;
}) {
  const admin = currentRole === "admin";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Rules</h1>
        {admin ? (
          <>
            <Button onClick={() => onImport()}>Import JSON</Button>
            <Button onClick={() => onExport()}>Export JSON</Button>
            <Link className="rounded bg-slate-900 px-3 py-2 text-sm text-white" href="/rules/new">
              New rule
            </Link>
          </>
        ) : (
          <span className="text-sm text-slate-500">View only</span>
        )}
      </div>
      <section aria-label="Rule filters" className="flex flex-wrap gap-3 rounded border border-slate-200 p-3 text-sm dark:border-slate-700">
        <Input
          aria-label="Search rules"
          placeholder="Search rules"
          value={filters.search}
          onChange={(event) => onFiltersChange({ ...filters, search: event.target.value })}
        />
        <label className="inline-flex items-center gap-1">
          Kind
          <select
            aria-label="Rule kind"
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.kind}
            onChange={(event) => onFiltersChange({ ...filters, kind: event.target.value })}
          >
            <option value="">all</option>
            <option value="threshold">threshold</option>
            <option value="sequence">sequence</option>
            <option value="field_match">field_match</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1">
          <input
            type="checkbox"
            aria-label="Noisy rules"
            checked={filters.noisy}
            onChange={(event) => onFiltersChange({ ...filters, noisy: event.target.checked })}
          />
          Noisy (top by findings/day)
        </label>
      </section>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Detection rules</caption>
          <thead>
            <tr>
              <th scope="col">Enabled</th>
              <th scope="col">Name</th>
              <th scope="col">Kind</th>
              <th scope="col">Summary</th>
              <th scope="col">Severities</th>
              <th scope="col">Findings 24h / 7d</th>
              <th scope="col">Version</th>
              {admin ? <th scope="col">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id} className="border-b border-slate-100 dark:border-slate-800">
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Enable ${rule.name}`}
                    checked={rule.enabled}
                    disabled={!admin}
                    onChange={(event) => onToggle(rule.id, event.target.checked)}
                  />
                </td>
                <td>
                  <Link className="text-blue-700 underline dark:text-blue-300" href={`/rules/${rule.id}`}>
                    {rule.name}
                  </Link>
                  <span className="ml-2 text-xs text-slate-500">
                    {rule.builtin ? "built-in" : "custom"}
                    {rule.modified ? " · modified" : ""}
                  </span>
                </td>
                <td>{rule.kind}</td>
                <td>{rule.summary ?? "—"}</td>
                <td>{rule.tier_severities?.join(", ") ?? "—"}</td>
                <td>{rule.findings_24h ?? 0} / {rule.findings_7d ?? 0}</td>
                <td>{rule.version ?? 1}</td>
                {admin ? (
                  <td className="flex gap-1">
                    <Button onClick={() => onDuplicate(rule.id)}>Duplicate</Button>
                    {rule.builtin ? (
                      <Button onClick={() => onReset(rule.id)}>Reset</Button>
                    ) : (
                      <Button onClick={() => onDelete(rule.id)}>Delete</Button>
                    )}
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

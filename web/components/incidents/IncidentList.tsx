"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { MitreBadge, RiskScoreMeter } from "@/components/badges/ExplanationBadges";
import { SeverityBadge } from "@/components/badges/SeverityBadge";
import { Button, Input, Label } from "@/components/ui/primitives";
import type { IncidentRecord } from "@/lib/api/hooks";
import type { Role } from "@/lib/auth";
import {
  type IncidentFilters,
  emptyIncidentFilters,
  incidentFiltersToSearch,
} from "@/lib/incident/filters";

const STATUSES = ["open", "investigating", "resolved", "false_positive", "closed", "merged"];
const SEVERITIES = ["low", "medium", "high", "critical"];

export function IncidentList({
  incidents,
  filters,
  onFiltersChange,
  onBulkStatus,
  currentRole,
  highlightedIds,
  nextCursor,
  onPage,
  onPrevious,
}: {
  incidents: IncidentRecord[];
  filters: IncidentFilters;
  onFiltersChange: (filters: IncidentFilters) => void;
  onBulkStatus: (ids: number[], status: string, reason: string) => void;
  currentRole: Role;
  highlightedIds?: Set<number>;
  nextCursor?: string | null;
  onPage?: (cursor: string) => void;
  onPrevious?: () => void;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkStatus, setBulkStatus] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const search = incidentFiltersToSearch(filters);
    window.history.replaceState(null, "", `/incidents${search ? `?${search}` : ""}`);
  }, [filters]);

  const toggle = (key: "status" | "severity", value: string) => {
    const current = filters[key];
    onFiltersChange({
      ...filters,
      [key]: current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    });
  };

  const confirmBulk = () => {
    if (!bulkStatus || selected.size === 0) return;
    onBulkStatus([...selected], bulkStatus, reason);
    setBulkOpen(false);
    setBulkStatus(null);
    setReason("");
    setConfirmation("");
    setSelected(new Set());
  };

  const needsTypedConfirmation = selected.size > 10;
  const canConfirm = reason.trim().length > 0 && (!needsTypedConfirmation || confirmation === "confirm");

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Incidents</h1>
      <section aria-label="Incident filters" className="flex flex-wrap gap-4 rounded border border-slate-200 p-3 text-sm dark:border-slate-700">
        <fieldset>
          <legend className="font-medium">Status</legend>
          <div className="flex flex-wrap gap-2">
            {STATUSES.map((status) => (
              <label key={status} className="inline-flex items-center gap-1">
                <input
                  type="checkbox"
                  aria-label={`Status ${status}`}
                  checked={filters.status.includes(status)}
                  onChange={() => toggle("status", status)}
                />
                {status.replaceAll("_", " ")}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend className="font-medium">Severity</legend>
          <div className="flex flex-wrap gap-2">
            {SEVERITIES.map((severity) => (
              <label key={severity} className="inline-flex items-center gap-1">
                <input
                  type="checkbox"
                  aria-label={`Severity ${severity}`}
                  checked={filters.severity.includes(severity)}
                  onChange={() => toggle("severity", severity)}
                />
                {severity}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="inline-flex items-center gap-1" htmlFor="incident-assignee">
          Assignee
          <Input
            id="incident-assignee"
            aria-label="Assignee filter"
            value={filters.assignee}
            onChange={(event) => onFiltersChange({ ...filters, assignee: event.target.value })}
          />
        </label>
        <label className="inline-flex items-center gap-1" htmlFor="incident-search">
          Search
          <Input
            id="incident-search"
            aria-label="Search incidents"
            value={filters.search}
            onChange={(event) => onFiltersChange({ ...filters, search: event.target.value })}
          />
        </label>
        <label className="inline-flex items-center gap-1" htmlFor="incident-since">
          Since
          <Input
            id="incident-since"
            aria-label="Incident since"
            value={filters.since}
            onChange={(event) => onFiltersChange({ ...filters, since: event.target.value })}
            placeholder="2026-11-19T00:00:00+00:00"
          />
        </label>
        <label className="inline-flex items-center gap-1" htmlFor="incident-until">
          Until
          <Input
            id="incident-until"
            aria-label="Incident until"
            value={filters.until}
            onChange={(event) => onFiltersChange({ ...filters, until: event.target.value })}
            placeholder="2026-11-20T00:00:00+00:00"
          />
        </label>
        <label className="inline-flex items-center gap-1">
          Sort
          <select
            aria-label="Sort"
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.sort}
            onChange={(event) =>
              onFiltersChange({ ...filters, sort: event.target.value as "risk" | "recent" })
            }
          >
            <option value="risk">risk</option>
            <option value="recent">recent</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1">
          <input
            type="checkbox"
            aria-label="Needs attention"
            checked={filters.needsAttention}
            onChange={(event) => onFiltersChange({ ...filters, needsAttention: event.target.checked })}
          />
          Needs attention
        </label>
        <Button
          onClick={() => {
            onFiltersChange(emptyIncidentFilters);
            setSelected(new Set());
          }}
        >
          Clear
        </Button>
      </section>

      {currentRole === "admin" ? (
        <section aria-label="Bulk actions" className="flex flex-wrap items-center gap-2">
          <Button disabled={selected.size === 0} onClick={() => setBulkOpen((value) => !value)}>
            Change status ({selected.size})
          </Button>
          <span className="text-sm text-slate-500">Change status</span>
          {bulkOpen ? (
            <div role="dialog" aria-label="Bulk status change" className="flex flex-wrap items-center gap-2 rounded border border-slate-300 p-2 dark:border-slate-600">
              <Label htmlFor="bulk-status">Target status</Label>
              <select
                id="bulk-status"
                aria-label="Bulk target status"
                className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                value={bulkStatus ?? ""}
                onChange={(event) => setBulkStatus(event.target.value)}
              >
                <option value="">Select…</option>
                {STATUSES.filter((status) => status !== "merged").map((status) => (
                  <option key={status} value={status}>{status.replaceAll("_", " ")}</option>
                ))}
              </select>
              <Label htmlFor="bulk-reason">Reason</Label>
              <Input id="bulk-reason" aria-label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
              {needsTypedConfirmation ? (
                <Input
                  aria-label="Type confirm"
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  placeholder={`Type confirm for ${selected.size} incidents`}
                />
              ) : null}
              <Button disabled={!bulkStatus || !canConfirm} onClick={confirmBulk}>Confirm</Button>
            </div>
          ) : null}
        </section>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">Incidents matching the current filters</caption>
          <thead className="sticky top-0 bg-white dark:bg-slate-900">
            <tr>
              {currentRole === "admin" ? <th scope="col">Select</th> : null}
              <th scope="col">Severity</th>
              <th scope="col">Score</th>
              <th scope="col">Title</th>
              <th scope="col">Status</th>
              <th scope="col">IP / user</th>
              <th scope="col">First / last seen</th>
              <th scope="col">Events</th>
              <th scope="col">Rules</th>
              <th scope="col">MITRE</th>
              <th scope="col">Assignee</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((incident) => (
              <tr
                key={incident.id}
                data-highlighted={highlightedIds?.has(incident.id) ? "true" : undefined}
                className={`border-b border-slate-100 dark:border-slate-800 ${
                  highlightedIds?.has(incident.id) ? "bg-blue-50 dark:bg-blue-950" : ""
                }`}
              >
                {currentRole === "admin" ? (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Select incident ${incident.id}`}
                      checked={selected.has(incident.id)}
                      onChange={() =>
                        setSelected((current) => {
                          const next = new Set(current);
                          if (next.has(incident.id)) next.delete(incident.id);
                          else next.add(incident.id);
                          return next;
                        })
                      }
                    />
                  </td>
                ) : null}
                <td><SeverityBadge severity={incident.severity} /></td>
                <td className="w-28"><RiskScoreMeter value={incident.score ?? incident.risk_score ?? 0} /></td>
                <td>
                  <Link className="text-blue-700 underline dark:text-blue-300" href={`/incidents/${incident.id}`}>
                    {incident.title ?? `Incident #${incident.id}`}
                  </Link>
                </td>
                <td>{incident.status.replaceAll("_", " ")}</td>
                <td>{incident.primary_ip ?? "—"} / {incident.primary_username ?? "—"}</td>
                <td>{incident.first_seen ?? "—"} / {incident.last_seen ?? "—"}</td>
                <td>{incident.event_ids?.length ?? 0}</td>
                <td>{incident.rules_fired?.slice(0, 3).join(", ") ?? "—"}</td>
                <td>
                  {incident.mitre?.slice(0, 2).map((technique) => (
                    <MitreBadge key={technique} technique={technique} />
                  ))}
                </td>
                <td>{incident.assignee ?? "unassigned"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {onPage || onPrevious ? (
        <nav aria-label="Incident pagination" className="flex gap-2">
          <Button disabled={!onPrevious} onClick={() => onPrevious?.()}>Previous</Button>
          <Button disabled={!nextCursor} onClick={() => nextCursor && onPage?.(nextCursor)}>Next</Button>
        </nav>
      ) : null}
    </div>
  );
}

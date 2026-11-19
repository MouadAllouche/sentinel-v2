"use client";

import Link from "next/link";
import { useEffect } from "react";

import { BaselineBandChart } from "@/components/charts/BaselineBandChart";
import { Card, Skeleton } from "@/components/ui/primitives";
import { bandSeries, maturityText } from "@/lib/admin/helpers";
import type { Role } from "@/lib/auth";

const METRICS = [
  "failed_logins_per_hour", "successful_logins_by_user", "connections_by_process",
  "distinct_destinations_by_process", "sudo_by_user", "known_login_ips",
];

export interface BehaviorFilters {
  metric: string;
  subject: string;
  range: string;
}

export function BehaviorPage({
  filters,
  onFiltersChange,
  baselines,
  anomalies,
  knownIps,
  role,
}: {
  filters: BehaviorFilters;
  onFiltersChange: (filters: BehaviorFilters) => void;
  baselines: Array<{
    metric?: string; subject?: string; samples?: number; status?: string;
    mean?: number; stddev?: number;
  }>;
  anomalies: Array<{
    id: number; timestamp: string; metric?: string; subject?: string; observed?: number;
    mean?: number; stddev?: number; z?: number; description?: string; severity?: string;
  }>;
  knownIps: Array<{ username?: string; value?: string; source_ip?: string; first_seen?: string; last_seen?: string }>;
  role: Role;
}) {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams({
      metric: filters.metric, subject: filters.subject, range: filters.range,
    });
    window.history.replaceState(null, "", `/behavior?${params}`);
  }, [filters]);

  const baseline = baselines[0] ?? {};
  const samples = Number(baseline.samples ?? 0);
  const series = bandSeries(
    anomalies.map((item) => ({ timestamp: item.timestamp, value: Number(item.observed ?? 0) })),
    { mean: Number(baseline.mean ?? 0), stddev: Number(baseline.stddev ?? 0) },
    [1, 3],
  );

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Behavior monitoring</h1>
      <section aria-label="Behavior filters" className="flex flex-wrap gap-3 rounded border border-slate-200 p-3 text-sm dark:border-slate-700">
        <label className="inline-flex items-center gap-1">
          Metric
          <select
            aria-label="Metric"
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.metric}
            onChange={(event) => onFiltersChange({ ...filters, metric: event.target.value })}
          >
            {METRICS.map((metric) => <option key={metric} value={metric}>{metric}</option>)}
          </select>
        </label>
        <label className="inline-flex items-center gap-1">
          Subject
          <input
            aria-label="Subject"
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.subject}
            onChange={(event) => onFiltersChange({ ...filters, subject: event.target.value })}
            list="subject-options"
          />
          <datalist id="subject-options">
            {baselines.map((item, index) => <option key={index} value={String(item.subject ?? "")} />)}
          </datalist>
        </label>
        <label className="inline-flex items-center gap-1">
          Range
          <select
            aria-label="Behavior range"
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.range}
            onChange={(event) => onFiltersChange({ ...filters, range: event.target.value })}
          >
            <option value="24h">24 h</option><option value="7d">7 d</option><option value="30d">30 d</option>
          </select>
        </label>
      </section>

      <div className="grid gap-3 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-2 font-semibold">Values against baseline</h2>
          <BaselineBandChart
            series={series.map((row) => ({
              timestamp: row.timestamp, value: row.value, mean: row.mean, stddev: row.stddev,
              upper: row.upper3, lower: row.lower3,
            }))}
            maturity={samples >= 24 ? "mature" : "immature"}
            reason={maturityText(samples, 24)}
          />
        </Card>
        <Card>
          <h2 className="font-semibold">Maturity</h2>
          <p role="status" className="mt-2 text-sm">
            {baseline.metric ?? filters.metric}: {maturityText(samples, 24)}
          </p>
          {role === "admin" ? (
            <Link className="mt-2 inline-block text-sm text-blue-700 underline" href={`/rules/new?template=baseline_metric&metric=${encodeURIComponent(filters.metric)}`}>
              Edit thresholds
            </Link>
          ) : null}
        </Card>
      </div>

      <Card>
        <h2 className="mb-2 font-semibold">Anomalies</h2>
        {anomalies.length === 0 ? <Skeleton rows={2} /> : (
          <ul className="space-y-2 text-sm">
            {anomalies.map((item) => (
              <li key={item.id} className="rounded border border-slate-200 p-2 dark:border-slate-700">
                <p className="font-medium">{item.metric ?? "metric"} / {item.subject ?? "global"}</p>
                <p>Observed {item.observed}; expected mean {item.mean}, stddev {item.stddev}.</p>
                <p>{item.description ?? "An unusual value was observed."}</p>
                <p className="text-xs text-amber-800 dark:text-amber-200">
                  Unusual is not necessarily malicious.
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <h2 className="mb-2 font-semibold">Known login IPs per user</h2>
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Known login IPs</caption>
          <thead><tr><th scope="col">User</th><th scope="col">IP</th><th scope="col">First seen</th><th scope="col">Last seen</th></tr></thead>
          <tbody>
            {knownIps.map((item, index) => (
              <tr key={index} className="border-b border-slate-100 dark:border-slate-800">
                <td>{String(item.username ?? item.value ?? "")}</td>
                <td>{String(item.source_ip ?? "")}</td>
                <td>{String(item.first_seen ?? "—")}</td>
                <td>{String(item.last_seen ?? "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

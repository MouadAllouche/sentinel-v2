"use client";

import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { useState } from "react";

import { Card, Skeleton } from "@/components/ui/primitives";
import { useEventStats } from "@/lib/api/hooks";
import { rangeForPreset } from "@/lib/filters";

const SEVERITIES = ["low", "medium", "high", "critical"] as const;

export function EventsOverTime({ now = new Date().toISOString() }: { now?: string }) {
  const [range, setRange] = useState("24h");
  const { since, until } = rangeForPreset(range, now);
  const query = useEventStats({
    bucket: range === "24h" ? "hour" : "day",
    group_by: "severity",
    since,
    until,
  });
  const rows = Object.values(
    (query.data ?? []).reduce<Record<string, Record<string, string | number>>>((byBucket, item) => {
      const row = (byBucket[item.bucket] ??= { bucket: item.bucket });
      row[item.severity] = item.total;
      return byBucket;
    }, {}),
  );

  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Events over time</h2>
        <label className="text-sm">
          Range
          <select
            aria-label="Time range"
            className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={range}
            onChange={(event) => setRange(event.target.value)}
          >
            <option value="24h">24 h</option>
            <option value="7d">7 d</option>
            <option value="30d">30 d</option>
          </select>
        </label>
      </div>
      {query.isLoading ? (
        <Skeleton rows={3} />
      ) : rows.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">No events in this range.</p>
      ) : (
        <>
          <div aria-hidden="true" className="mt-2 h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows}>
                <XAxis hide dataKey="bucket" />
                <YAxis hide />
                {SEVERITIES.map((severity) => (
                  <Bar
                    key={severity}
                    dataKey={severity}
                    stackId="severity"
                    fill={
                      { low: "#64748b", medium: "#f59e0b", high: "#f97316", critical: "#dc2626" }[
                        severity
                      ]
                    }
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="mt-2 w-full text-left text-sm">
            <caption className="sr-only">Events by bucket and severity</caption>
            <thead>
              <tr>
                <th scope="col">Bucket (UTC)</th>
                {SEVERITIES.map((severity) => (
                  <th key={severity} scope="col">{severity}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={String(row.bucket)}>
                  <td>{String(row.bucket)}</td>
                  {SEVERITIES.map((severity) => (
                    <td key={severity}>{Number(row[severity] ?? 0)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Card>
  );
}

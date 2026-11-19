"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface BaselinePoint {
  timestamp: string;
  value: number;
  mean: number;
  stddev: number;
  upper: number;
  lower: number;
}

/**
 * Value line with a mean ± zσ band and an accessible fallback table. An
 * immature baseline is labelled explicitly and never shown as "all clear".
 */
export function BaselineBandChart({
  series,
  maturity,
  reason,
}: {
  series: BaselinePoint[];
  maturity: "mature" | "immature";
  reason?: string;
}) {
  if (maturity !== "mature" || series.length === 0) {
    return (
      <div role="status" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
        <p className="font-medium">Not enough data to judge this baseline.</p>
        {reason ? <p className="mt-1">{reason}</p> : null}
      </div>
    );
  }

  return (
    <div>
      <div aria-hidden="true" className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis hide dataKey="timestamp" />
            <YAxis hide />
            <Tooltip />
            <Line type="monotone" dataKey="upper" stroke="#94a3b8" dot={false} />
            <Line type="monotone" dataKey="lower" stroke="#94a3b8" dot={false} />
            <Line type="monotone" dataKey="mean" stroke="#2563eb" dot={false} />
            <Line type="monotone" dataKey="value" stroke="#dc2626" dot />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <table className="mt-2 w-full text-left text-sm">
        <caption className="sr-only">Baseline values with expected band</caption>
        <thead>
          <tr>
            <th scope="col">Time (UTC)</th>
            <th scope="col">Value</th>
            <th scope="col">Mean</th>
            <th scope="col">Upper band</th>
            <th scope="col">Lower band</th>
          </tr>
        </thead>
        <tbody>
          {series.map((point) => (
            <tr key={point.timestamp}>
              <td>{point.timestamp}</td>
              <td>{point.value}</td>
              <td>{point.mean}</td>
              <td>{point.upper}</td>
              <td>{point.lower}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-xs text-slate-500">
        Band is expected behaviour, not an allowlist. Points outside it are observations to review.
      </p>
    </div>
  );
}

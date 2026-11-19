"use client";

import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

/** Charts are decorative; every chart has an equivalent accessible table. */
export function TimeSeriesChart({
  series,
  label = "Time series",
}: {
  series: Array<{ timestamp: string; value: number }>;
  label?: string;
}) {
  if (series.length === 0) return <p className="text-sm text-slate-500">No data for {label}.</p>;
  return (
    <div>
      <div aria-hidden="true" className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series}>
            <XAxis hide dataKey="timestamp" />
            <YAxis hide />
            <Line type="monotone" dataKey="value" stroke="#2563eb" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <FallbackTable rows={series} />
    </div>
  );
}

export function StackedBarChart({
  series,
}: {
  series: Array<{ label: string; low?: number; medium?: number; high?: number; critical?: number }>;
}) {
  if (series.length === 0) return <p className="text-sm text-slate-500">No data to stack.</p>;
  return (
    <div>
      <div aria-hidden="true" className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={series}>
            <XAxis hide dataKey="label" />
            <YAxis hide />
            <Bar dataKey="low" stackId="s" fill="#64748b" />
            <Bar dataKey="medium" stackId="s" fill="#f59e0b" />
            <Bar dataKey="high" stackId="s" fill="#f97316" />
            <Bar dataKey="critical" stackId="s" fill="#dc2626" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <FallbackTable rows={series} />
    </div>
  );
}

const PIE_COLOURS = ["#2563eb", "#f59e0b", "#f97316", "#dc2626", "#64748b"];

export function DonutChart({ series }: { series: Array<{ label: string; value: number }> }) {
  if (series.length === 0) return <p className="text-sm text-slate-500">No distribution yet.</p>;
  return (
    <div>
      <div aria-hidden="true" className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={series} dataKey="value" nameKey="label" innerRadius={40} outerRadius={70}>
              {series.map((item, index) => (
                <Cell key={item.label} fill={PIE_COLOURS[index % PIE_COLOURS.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <FallbackTable rows={series} />
    </div>
  );
}

function FallbackTable({ rows }: { rows: Array<Record<string, string | number>> }) {
  const columns = Object.keys(rows[0] ?? {});
  return (
    <table className="mt-2 w-full text-left text-sm">
      <caption className="sr-only">Chart data in table form</caption>
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column} scope="col">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {columns.map((column) => (
              <td key={column}>{String(row[column] ?? "—")}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

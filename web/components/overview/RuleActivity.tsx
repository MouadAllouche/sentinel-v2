"use client";

import Link from "next/link";

import { Card, Skeleton } from "@/components/ui/primitives";
import { useFindings } from "@/lib/api/hooks";

export function RuleActivity() {
  const findings = useFindings();
  const grouped = Object.entries(
    (findings.data ?? []).reduce<Record<string, number>>((counts, item) => {
      const id = String(item.rule_id ?? "unknown");
      counts[id] = (counts[id] ?? 0) + 1;
      return counts;
    }, {}),
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <Card>
      <h2 className="mb-2 text-lg font-semibold">Rule activity</h2>
      {findings.isLoading ? (
        <Skeleton rows={3} />
      ) : grouped.length === 0 ? (
        <p className="text-sm text-slate-500">No rule findings yet.</p>
      ) : (
        <ul className="space-y-2 text-sm" aria-label="Findings by rule">
          {grouped.map(([ruleId, count]) => (
            <li key={ruleId} className="flex items-center gap-2">
              <Link className="truncate text-blue-700 underline dark:text-blue-300" href={`/rules/${ruleId}`}>
                {ruleId}
              </Link>
              <span className="ml-auto tabular-nums">{count}</span>
              <svg width="48" height="12" role="img" aria-label={`${count} findings`}>
                <rect width={Math.min(48, count * 4)} height="12" fill="#2563eb" />
              </svg>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

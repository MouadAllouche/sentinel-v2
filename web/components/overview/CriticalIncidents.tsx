"use client";

import Link from "next/link";

import { MitreBadge, RiskScoreMeter } from "@/components/badges/ExplanationBadges";
import { SeverityBadge } from "@/components/badges/SeverityBadge";
import { Card, Skeleton } from "@/components/ui/primitives";
import { useIncidents, useRiskThresholds } from "@/lib/api/hooks";
import { mitreKey } from "@/lib/mitre";

export function CriticalIncidents() {
  const incidents = useIncidents();
  const thresholds = useRiskThresholds();
  const top = [...(incidents.data ?? [])]
    .filter((item) => item.status !== "closed")
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 5);

  return (
    <Card>
      <h2 className="mb-2 text-lg font-semibold">Highest-risk open incidents</h2>
      {incidents.isLoading ? (
        <Skeleton rows={3} />
      ) : top.length === 0 ? (
        <p className="text-sm text-slate-500">No open incidents.</p>
      ) : (
        <ol className="space-y-3" aria-label="Highest-risk incidents">
          {top.map((incident) => (
            <li key={incident.id} className="rounded border border-slate-200 p-2 dark:border-slate-700">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={incident.severity} />
                <Link className="font-medium text-blue-700 underline dark:text-blue-300" href={`/incidents/${incident.id}`}>
                  {incident.title ?? `Incident #${incident.id}`}
                </Link>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                First seen {incident.first_seen ?? incident.created_at ?? "unknown"} · last seen{" "}
                {incident.last_seen ?? "on the detail page"}
              </p>
              <div className="mt-2 max-w-xs">
                <RiskScoreMeter value={incident.score ?? 0} thresholds={thresholds.data} />
              </div>
              {incident.mitre?.length ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {incident.mitre.map((technique) => (
                    <MitreBadge key={mitreKey(technique)} technique={technique} />
                  ))}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

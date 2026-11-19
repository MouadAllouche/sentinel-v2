"use client";

import { Card, Skeleton } from "@/components/ui/primitives";
import { RiskScoreMeter } from "@/components/badges/ExplanationBadges";
import {
  useEvents,
  useHealth,
  useIncidents,
  useRiskThresholds,
  useRules,
} from "@/lib/api/hooks";

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </Card>
  );
}

export function OverviewCards() {
  const health = useHealth();
  const events = useEvents({ limit: 1 });
  const incidents = useIncidents();
  const rules = useRules();
  const thresholds = useRiskThresholds();

  if (health.isLoading) return <Skeleton rows={4} />;

  const openIncidents = (incidents.data ?? []).filter((item) => item.status !== "closed").length;
  const highestScore = (incidents.data ?? []).reduce(
    (maximum, item) => Math.max(maximum, item.score ?? 0),
    0,
  );

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Overview</h1>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Engine health" value={health.data?.status ?? "unknown"} />
        <Metric label="Recent events" value={events.data?.items.length ? "available" : 0} />
        <Metric label="Open incidents" value={openIncidents} />
        <Metric label="Active rules" value={rules.data?.filter((rule) => rule.enabled).length ?? 0} />
      </div>
      <Card className="max-w-md">
        <h2 className="text-sm font-medium">Highest incident score (observed)</h2>
        <RiskScoreMeter value={highestScore} thresholds={thresholds.data} />
        <p className="mt-2 text-xs text-slate-500">Bands are read from /api/risk/thresholds.</p>
      </Card>
    </div>
  );
}

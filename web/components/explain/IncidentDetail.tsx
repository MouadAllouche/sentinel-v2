"use client";

import { useParams } from "next/navigation";

import { FactInferenceBadge, RiskScoreMeter } from "@/components/badges/ExplanationBadges";
import { SeverityBadge } from "@/components/badges/SeverityBadge";
import { Card, ErrorState, Skeleton } from "@/components/ui/primitives";
import {
  useIncident,
  useIncidentExplanation,
  useIncidentTimeline,
  useRiskThresholds,
} from "@/lib/api/hooks";

export function IncidentDetail() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const detail = useIncident(id);
  const timeline = useIncidentTimeline(id);
  const explanation = useIncidentExplanation(id);
  const thresholds = useRiskThresholds();

  if (!Number.isFinite(id)) return <ErrorState message="Invalid incident id." />;
  if (detail.isLoading || timeline.isLoading) return <Skeleton rows={5} />;
  if (detail.isError) return <ErrorState message="Could not load this incident." />;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Incident #{id}</h1>
      <div className="grid gap-3 lg:grid-cols-3">
        <Card>
          <SeverityBadge severity={detail.data?.severity ?? "low"} />
          <p className="mt-2 text-sm">Status: {detail.data?.status ?? "unknown"}</p>
          <p className="text-sm">Assignee: {detail.data?.assignee ?? "unassigned"}</p>
        </Card>
        <Card>
          <RiskScoreMeter value={detail.data?.score ?? 0} thresholds={thresholds.data} />
          <p className="mt-2 text-xs text-slate-500">Score bands come from /api/risk/thresholds.</p>
        </Card>
        <Card>
          <h2 className="font-semibold">Explanation</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            {String(explanation.data?.summary ?? "No explanation is available for this incident.")}
          </p>
        </Card>
      </div>
      <Card>
        <h2 className="mb-2 font-semibold">Timeline</h2>
        {timeline.data?.length ? (
          <ol className="space-y-2" aria-label="Incident timeline">
            {timeline.data.map((entry, index) => (
              <li key={index} className="flex items-start gap-2 border-b border-slate-100 py-1 text-sm dark:border-slate-800">
                <FactInferenceBadge kind={entry.fact === false ? "inference" : "fact"} />
                <span className="tabular-nums text-slate-500">{entry.timestamp}</span>
                <span>{entry.summary}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-slate-500">No timeline entries.</p>
        )}
      </Card>
    </div>
  );
}

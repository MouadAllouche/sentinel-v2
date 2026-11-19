"use client";

import { useState } from "react";

import { BehaviorPage, type BehaviorFilters } from "@/components/behavior/BehaviorPage";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import { useApiList } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";

const initial: BehaviorFilters = { metric: "failed_logins_per_hour", subject: "", range: "24h" };

export function BehaviorRoute() {
  const [filters, setFilters] = useState<BehaviorFilters>(() => {
    if (typeof window === "undefined") return initial;
    const params = new URLSearchParams(window.location.search);
    return {
      metric: params.get("metric") ?? initial.metric,
      subject: params.get("subject") ?? "",
      range: params.get("range") ?? "24h",
    };
  });
  const me = useMe();
  const baselines = useApiList<Record<string, unknown>>("/api/baselines");
  const anomalies = useApiList<Record<string, unknown>>("/api/anomalies");
  const top = useApiList<Record<string, unknown>>("/api/events/top");
  const known = useApiList<Record<string, unknown>>("/api/baselines/series");

  if (baselines.isLoading || anomalies.isLoading) return <Skeleton rows={5} />;
  if (baselines.isError || anomalies.isError) {
    return <ErrorState message="Could not load behavior data." />;
  }
  return (
    <BehaviorPage
      filters={filters}
      onFiltersChange={setFilters}
      baselines={baselines.data?.items ?? []}
      anomalies={(anomalies.data?.items ?? []) as Array<{
        id: number; timestamp: string; metric?: string; subject?: string; observed?: number;
        mean?: number; stddev?: number; z?: number; description?: string; severity?: string;
      }>}
      knownIps={top.data?.items ?? known.data?.items ?? []}
      role={me.role}
    />
  );
}

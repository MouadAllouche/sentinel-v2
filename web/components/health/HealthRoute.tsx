"use client";

import { HealthPage } from "@/components/health/HealthPage";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import { useApiList, useHealthFull } from "@/lib/api/hooks";

export function HealthRoute() {
  const health = useHealthFull();
  const cycles = useApiList<Record<string, unknown>>("/api/cycles");
  const collectors = useApiList<Record<string, unknown>>("/api/collectors");
  if (health.isLoading) return <Skeleton rows={4} />;
  if (health.isError) return <ErrorState message="Could not load health." />;
  return (
    <HealthPage
      health={health.data ?? { status: "unknown" }}
      cycles={(cycles.data?.items ?? []) as Array<{
        id: number; started_at: string; status: string; steps_json?: string;
      }>}
      collectors={(collectors.data?.items ?? []) as Array<{
        name?: string; status?: string; warnings?: string[]; events?: number;
      }>}
    />
  );
}

"use client";

import { JsonViewer } from "@/components/explain/JsonViewer";
import { Card, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useHealth } from "@/lib/api/hooks";

export function HealthPanel() {
  const health = useHealth();
  if (health.isLoading) return <Skeleton rows={3} />;
  if (health.isError) return <ErrorState message="Could not read engine health." onRetry={() => void health.refetch()} />;

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Health</h1>
      <Card>
        <p className="text-sm">Engine status: <strong>{health.data?.status ?? "unknown"}</strong></p>
        <div className="mt-2 text-xs text-slate-600 dark:text-slate-300">
          <JsonViewer value={health.data} />
        </div>
      </Card>
    </div>
  );
}

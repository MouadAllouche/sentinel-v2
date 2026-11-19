import Link from "next/link";

import { Card } from "@/components/ui/primitives";

export function HealthStrip({
  health,
  collectors,
  baselines,
  notificationsEnabled,
  now,
}: {
  health?: {
    status?: string;
    db?: { size_bytes?: number };
    last_cycle?: { started_at?: string; status?: string } | null;
  } | null;
  collectors: Array<{ name: string; status: string; warnings?: string[] }>;
  baselines?: { mature: number; total: number };
  notificationsEnabled: boolean;
  now?: string;
}) {
  const cycle = health?.last_cycle;
  const reference = now ? new Date(now).getTime() : undefined;
  const cycleAge =
    cycle?.started_at && reference !== undefined
      ? `${Math.max(0, Math.round((reference - new Date(cycle.started_at).getTime()) / 60000))} min ago`
      : "unknown";
  const dbSize = health?.db?.size_bytes
    ? `${Math.round(health.db.size_bytes / 1024)} KiB`
    : "unknown";
  const warnings = collectors.flatMap((collector) =>
    (collector.warnings ?? []).map((warning) => `${collector.name}: ${warning}`),
  );
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span>Engine: <strong>{health?.status ?? "unknown"}</strong></span>
        <span>Last cycle: {cycleAge}{cycle?.status ? ` (${cycle.status})` : ""}</span>
        <span>DB size: {dbSize}</span>
        <span>
          Collectors: {collectors.filter((item) => item.status === "ok").length}/{collectors.length} ok
        </span>
        <span>Baselines: {baselines ? `learning: ${baselines.mature}/${baselines.total} h` : "learning"}</span>
        <span>Notifications: {notificationsEnabled ? "enabled" : "disabled"}</span>
        <Link className="text-blue-700 underline" href="/health">
          Health details
        </Link>
      </div>
      {warnings.length ? (
        <ul className="mt-2 list-disc pl-5 text-sm text-amber-800 dark:text-amber-200" aria-label="Collector warnings">
          {warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

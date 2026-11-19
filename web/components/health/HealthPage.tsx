import { Card } from "@/components/ui/primitives";
import { healthHints } from "@/lib/admin/helpers";

export function HealthPage({
  health,
  cycles,
  collectors,
}: {
  health: {
    status: string;
    reasons?: string[];
    db?: { size_bytes?: number; event_count?: number; oldest_event?: string };
    last_cycle?: Record<string, unknown> | null;
  };
  cycles: Array<{ id: number; started_at: string; status: string; steps_json?: string }>;
  collectors: Array<{ name?: string; status?: string; warnings?: string[]; events?: number }>;
}) {
  const hints = healthHints(health.reasons ?? []);
  const last = cycles[0];
  const steps = last?.steps_json ? (JSON.parse(last.steps_json) as Array<{ name?: string; duration_ms?: number }>) : [];
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Health</h1>
      <Card>
        <h2 className="font-semibold">Status: {health.status}</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          DB size: {health.db?.size_bytes ?? 0} bytes · events: {health.db?.event_count ?? 0} ·
          oldest event: {health.db?.oldest_event ?? "—"}
        </p>
      </Card>
      <Card>
        <h2 className="font-semibold">Last engine cycle</h2>
        <p className="text-sm">{last ? `${last.started_at} — ${last.status}` : "No cycle has run yet."}</p>
        <ul className="mt-2 text-sm">
          {steps.map((step, index) => (
            <li key={index}>{step.name ?? "step"}: {step.duration_ms ?? 0} ms</li>
          ))}
        </ul>
      </Card>
      <Card>
        <h2 className="font-semibold">Collectors</h2>
        <ul className="mt-2 space-y-1 text-sm">
          {collectors.map((collector, index) => (
            <li key={index}>
              {collector.name ?? "collector"}: {collector.status ?? "unknown"} · {collector.events ?? 0} events
              {collector.warnings?.length ? ` · ${collector.warnings.join("; ")}` : ""}
            </li>
          ))}
        </ul>
      </Card>
      {hints.length ? (
        <Card>
          <h2 className="font-semibold">How to fix</h2>
          <ul className="mt-2 list-disc pl-5 text-sm">
            {hints.map((hint, index) => <li key={index}>{hint}</li>)}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

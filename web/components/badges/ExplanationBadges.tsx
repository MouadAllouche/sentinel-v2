import { cn } from "@/lib/utils";

/** Observed facts and inferred claims are always visually and textually distinct. */
export function FactInferenceBadge({ kind }: { kind: "fact" | "inference" }) {
  const fact = kind === "fact";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium",
        fact
          ? "border border-solid bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900"
          : "border border-dashed border-slate-500 text-slate-700 dark:text-slate-300",
      )}
    >
      {fact ? "Observed" : "Inferred"}
    </span>
  );
}

/** MITRE references are indicative, never a confirmation of an attack. */
export function MitreBadge({ technique }: { technique: string }) {
  return (
    <a
      className="inline-flex items-center gap-1 rounded border border-violet-300 px-2 py-0.5 text-xs text-violet-800 underline decoration-dotted hover:bg-violet-50 dark:border-violet-700 dark:text-violet-200"
      href={`https://attack.mitre.org/techniques/${encodeURIComponent(technique)}/`}
      target="_blank"
      rel="noopener noreferrer"
    >
      {technique} <span className="sr-only">indicative mapping, opens MITRE ATT&amp;CK in a new tab</span>
      <span aria-hidden="true">(indicative)</span>
    </a>
  );
}

export function RiskScoreMeter({
  value,
  thresholds = { low: 25, medium: 50, high: 75 },
}: {
  value: number;
  thresholds?: { low: number; medium: number; high: number };
}) {
  const score = Math.min(100, Math.max(0, Math.round(value)));
  const band = score >= thresholds.high ? "critical" : score >= thresholds.medium ? "high" : score >= thresholds.low ? "medium" : "low";
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span>Risk score</span>
        <span className="font-semibold tabular-nums">{score} / 100</span>
      </div>
      <div
        className="mt-1 h-2 w-full overflow-hidden rounded bg-slate-200 dark:bg-slate-700"
        role="meter"
        aria-label="Risk score"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
        aria-valuetext={`${score} out of 100, ${band}`}
      >
        <div className="h-full bg-blue-600 dark:bg-blue-400" style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

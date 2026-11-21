export interface BandPoint {
  timestamp: string;
  value: number;
  mean: number;
  stddev: number;
  lower1: number;
  upper1: number;
  lower3: number;
  upper3: number;
  anomaly: boolean;
}

export function bandSeries(
  values: Array<{ timestamp: string; value: number }>,
  baseline: { mean: number; stddev: number },
  zLevels: number[],
  anomalyThreshold?: number,
): BandPoint[] {
  if (values.length === 0) return [];
  const byHour = new Map<string, number>();
  for (const point of values) byHour.set(point.timestamp.slice(0, 13), point.value);
  const hours = [...byHour.keys()].sort();
  const first = new Date(`${hours[0]}:00:00Z`).getTime();
  const last = new Date(`${hours.at(-1)!}:00:00Z`).getTime();
  const { mean, stddev } = baseline;
  const level3 = Math.max(...zLevels, 3);
  if (Number.isNaN(first) || Number.isNaN(last)) {
    return values.map((point) => ({
      timestamp: point.timestamp,
      value: point.value,
      mean,
      stddev,
      lower1: mean - stddev,
      upper1: mean + stddev,
      lower3: mean - level3 * stddev,
      upper3: mean + level3 * stddev,
      anomaly:
        anomalyThreshold !== undefined
          ? point.value >= anomalyThreshold
          : point.value > mean + level3 * stddev,
    }));
  }
  const rows: BandPoint[] = [];
  for (let stamp = first; stamp <= last; stamp += 3600000) {
    const label = new Date(stamp).toISOString().slice(0, 13);
    const value = byHour.get(label) ?? 0;
    rows.push({
      timestamp: `${label}:00:00+00:00`,
      value,
      mean,
      stddev,
      lower1: mean - stddev,
      upper1: mean + stddev,
      lower3: mean - level3 * stddev,
      upper3: mean + level3 * stddev,
      anomaly: anomalyThreshold !== undefined ? value >= anomalyThreshold : value > mean + level3 * stddev,
    });
  }
  return rows;
}

export function maturityText(samples: number, required: number): string {
  if (samples === 0) return "Not enough data yet — no anomalies will be reported";
  if (samples < required) {
    return `learning (${samples} of ${required} hours) — not enough data yet; no anomalies will be reported`;
  }
  return "mature";
}

export function validateEnvName(name: string): string | null {
  if (!/^[A-Z][A-Z0-9_]{2,63}$/.test(name)) {
    return "Use an uppercase environment variable name (letters, digits and underscores)";
  }
  return null;
}

export interface AuditDiff {
  path: string;
  kind: "added" | "removed" | "changed";
  before?: unknown;
  after?: unknown;
}

function flatten(value: unknown, prefix = ""): Record<string, unknown> {
  if (value === null || typeof value !== "object") return { [prefix]: value };
  if (Array.isArray(value)) {
    return value.reduce<Record<string, unknown>>((acc, item, index) => {
      Object.assign(acc, flatten(item, `${prefix}[${index}]`));
      return acc;
    }, {});
  }
  return Object.entries(value as Record<string, unknown>).reduce<Record<string, unknown>>(
    (acc, [key, child]) => {
      Object.assign(acc, flatten(child, prefix ? `${prefix}.${key}` : key));
      return acc;
    },
    {},
  );
}

export function auditDiff(before: unknown, after: unknown): AuditDiff[] {
  const left = flatten(before);
  const right = flatten(after);
  return [...new Set([...Object.keys(left), ...Object.keys(right)])]
    .filter((path) => JSON.stringify(left[path]) !== JSON.stringify(right[path]))
    .map((path) => {
      if (!(path in left)) return { path, kind: "added", after: right[path] };
      if (!(path in right)) return { path, kind: "removed", before: left[path] };
      return { path, kind: "changed", before: left[path], after: right[path] };
    });
}

export function passwordStrength(password: string): "weak" | "fair" | "strong" {
  if (password.length < 12) return "weak";
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((pattern) =>
    pattern.test(password),
  ).length;
  if (classes >= 3 && password.length >= 16) return "strong";
  return "fair";
}

export function retentionIssues(policy: Record<string, number>): string[] {
  const keys = ["low_days", "medium_days", "high_days", "critical_days"];
  const values = keys.map((key) => policy[key]).filter((value): value is number => value !== undefined);
  if (values.some((value) => value < 1)) return ["Ages must be positive"];
  // Higher severities may be kept for the same duration as the one below them
  // (the built-in default keeps high and critical evidence for 365 days).
  if (!values.every((value, index) => index === 0 || value >= values[index - 1]!)) {
    return ["Ages must be increasing or equal with severity"];
  }
  return [];
}

export function healthHints(warnings: string[]): string[] {
  return warnings.map((warning) => {
    if (/permission denied/i.test(warning)) {
      return `${warning} — add the service user to group adm (see docs/OPERATIONS.md); never use sudo from the app.`;
    }
    if (/stale/i.test(warning)) return `${warning} — check the engine process and scheduler.`;
    return `${warning} — review the collector documentation.`;
  });
}

export type WindowUnit = "seconds" | "minutes" | "hours" | "days";

export interface TierLike {
  label: string;
  count: number;
  window_seconds: number;
  severity: string;
  points: number;
}

export interface RuleLike {
  name?: string;
  match?: { event_types?: string[]; conditions?: unknown };
  group_by?: string[];
  tiers?: TierLike[];
}

const UNIT_SECONDS: Record<WindowUnit, number> = {
  seconds: 1,
  minutes: 60,
  hours: 3600,
  days: 86400,
};

/** Normalise a definition when the rule kind changes on create. */
export function definitionForKind<T extends {
  kind: string;
  tiers: TierLike[];
  z_tiers?: unknown[];
  steps?: Array<Record<string, unknown>>;
  correlate_on?: string[];
  within_seconds?: number;
  field?: string | null;
  per?: string | null;
  learning_days?: number;
  min_history_events?: number;
  metric?: string | null;
  subject?: string | null;
  min_std?: number;
  meta_conditions?: Array<Record<string, unknown>>;
}>(kind: string, current: T): T {
  const thresholdTiers = [{ label: "Medium", count: 5, window_seconds: 600, severity: "medium", points: 5 }];
  const zTiers = [{ label: "High", z: 3, min_absolute: 5, severity: "high", points: 20 }] as unknown as TierLike[];
  const tiers =
    kind === "threshold"
      ? current.tiers.length
        ? current.tiers
        : thresholdTiers
      : kind === "baseline_metric"
        ? current.tiers.length && "z" in (current.tiers[0] as object)
          ? current.tiers
          : zTiers
        : [];
  return {
    ...current,
    kind,
    tiers,
    z_tiers: kind === "baseline_metric" ? (current.z_tiers ?? []) : [],
    steps:
      kind === "sequence"
        ? current.steps?.length
          ? current.steps
          : [{ match: { event_types: ["failed_login"] }, min_count: 1, window_seconds: 600 }]
        : [],
    correlate_on:
      kind === "sequence"
        ? current.correlate_on?.length
          ? current.correlate_on
          : ["source_ip"]
        : [],
    within_seconds:
      kind === "sequence" && (current.within_seconds ?? 0) < 1 ? 3600 : (current.within_seconds ?? 0),
    metric: kind === "baseline_metric" ? (current.metric ?? "failed_login_count") : null,
    subject: kind === "baseline_metric" ? (current.subject ?? "source_ip") : null,
    min_std: kind === "baseline_metric" ? (current.min_std ?? 1) : 1,
    meta_conditions:
      kind === "incident_meta"
        ? current.meta_conditions?.length
          ? current.meta_conditions
          : [{ metric: "event_count", op: "gte", value: 5 }]
        : [],
    field: kind === "new_value" ? (current.field ?? "source_ip") : null,
    per: kind === "new_value" ? (current.per ?? "source_ip") : null,
    learning_days: kind === "new_value" ? (current.learning_days || 30) : 30,
    min_history_events: kind === "new_value" ? (current.min_history_events ?? 0) : 0,
  } as T;
}

export function windowToSeconds(value: number, unit: WindowUnit): number {
  return value * UNIT_SECONDS[unit];
}

export function secondsToWindow(seconds: number): { value: number; unit: WindowUnit } {
  for (const unit of ["days", "hours", "minutes"] as const) {
    if (seconds >= UNIT_SECONDS[unit] && seconds % UNIT_SECONDS[unit] === 0) {
      return { value: seconds / UNIT_SECONDS[unit], unit };
    }
  }
  return { value: seconds, unit: "seconds" };
}

function eventPhrase(types: string[]): string {
  const first = types[0] ?? "event";
  if (first === "failed_login") return "failed logins";
  return `${first} events`;
}

function groupPhrase(groups: string[]): string {
  const map: Record<string, string> = {
    source_ip: "from the same source IP",
    username: "from the same user",
    process_name: "from the same process",
    destination_ip: "to the same destination IP",
    file_path: "for the same file",
  };
  return groups.map((group) => map[group]).filter(Boolean).join(" ");
}

function windowPhrase(seconds: number): string {
  const { value, unit } = secondsToWindow(seconds);
  const label = value === 1 ? unit.slice(0, -1) : unit;
  return `${value} ${label}`;
}

export function tierSentence(
  tier: TierLike,
  match: { event_types?: string[]; group_by?: string[] } = {},
): string {
  const phrase = eventPhrase(match.event_types ?? []);
  const group = groupPhrase(match.group_by ?? []);
  const middle = group ? `${phrase} ${group}` : phrase;
  const suffix = tier.points ? ` (+${tier.points} points)` : "";
  return `If ≥ ${tier.count} ${middle} occur within ${windowPhrase(tier.window_seconds)} → ${tier.severity.toUpperCase()}${suffix}`;
}

function shortWindow(seconds: number): string {
  const { value, unit } = secondsToWindow(seconds);
  const label = { seconds: "s", minutes: "min", hours: "h", days: "d" }[unit];
  return `${value} ${label}`;
}

export function ruleSummary(rule: RuleLike): string {
  const types = rule.match?.event_types ?? [];
  const typeLabel = eventPhrase(types).replace(/^./, (char) => char.toUpperCase());
  const groupLabels: Record<string, string> = {
    source_ip: "source IP", username: "username", process_name: "process",
    destination_ip: "destination IP", file_path: "file path", source: "source",
  };
  const group = (rule.group_by ?? [])
    .map((item) => groupLabels[item] ?? item)
    .join(" and ");
  const tiers = (rule.tiers ?? [])
    .map((tier) => `≥${tier.count} in ${shortWindow(tier.window_seconds)} → ${tier.severity}`)
    .join("; ");
  return `${typeLabel}${group ? ` grouped by ${group}` : ""}: ${tiers}`;
}

export function roundTripDefinition(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value)) as unknown;
}

const OP_PHRASES: Record<string, string> = {
  eq: "equals", ne: "does not equal", in: "is in", not_in: "is not in",
  contains: "contains", not_contains: "does not contain", startswith: "starts with",
  endswith: "ends with", regex: "matches", gt: "is greater than", gte: "is at least",
  lt: "is less than", lte: "is at most", exists: "exists", not_exists: "does not exist",
  cidr_in: "is in", cidr_not_in: "is not in",
};

export function describeCondition(condition: unknown): string {
  if (!condition || typeof condition !== "object") return "";
  const node = condition as Record<string, unknown>;
  if (typeof node.field === "string") {
    const phrase = OP_PHRASES[String(node.op)] ?? String(node.op);
    const rendered =
      node.value === undefined
        ? ""
        : typeof node.value === "string"
          ? node.value
          : JSON.stringify(node.value);
    const value = rendered ? ` ${rendered}` : "";
    return `${node.field} ${phrase}${value}`;
  }
  const render = (key: "all" | "any" | "not") => {
    const children = node[key];
    if (!Array.isArray(children)) return "";
    const joiner = key === "any" ? " OR " : " AND ";
    const text = children.map(describeCondition).filter(Boolean).join(joiner);
    return key === "not" ? `NOT (${text})` : `(${text})`;
  };
  return render("all") || render("any") || render("not");
}

export function validateRegex(pattern: string): string | null {
  if (pattern.length > 200) return "must be at most 200 characters";
  if (/\([^)]*[+*][^)]*\)[+*{]/.test(pattern)) return "nested quantifiers are not allowed";
  let quantifiers = 0;
  let inClass = false;
  let escaped = false;
  for (let index = 0; index < pattern.length; index += 1) {
    const char = pattern[index]!;
    if (escaped) {
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (char === "[") inClass = true;
    else if (char === "]") inClass = false;
    else if (!inClass && (char === "*" || char === "+" || (char === "{" && /\{\d+,/.test(pattern.slice(index))))) {
      quantifiers += 1;
    }
  }
  if (quantifiers > 2) return "too many unbounded quantifiers";
  try {
    new RegExp(pattern);
    return null;
  } catch {
    return "invalid regular expression";
  }
}

export interface DiffEntry {
  path: string;
  before: unknown;
  after: unknown;
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

export function diffRules(before: unknown, after: unknown): DiffEntry[] {
  const left = flatten(before);
  const right = flatten(after);
  return [...new Set([...Object.keys(left), ...Object.keys(right)])]
    .filter((path) => JSON.stringify(left[path]) !== JSON.stringify(right[path]))
    .map((path) => ({ path, before: left[path], after: right[path] }));
}

export function mapServerErrors(
  details: Array<{ path: string; message: string }>,
  setError: (field: string, error: { message: string }) => void,
): void {
  for (const detail of details) {
    const field = detail.path.includes("name")
      ? "name"
      : detail.path.includes("tiers")
        ? "definition"
        : "definition";
    setError(field, { message: `${detail.path}: ${detail.message}` });
  }
}

export function validateThresholds(bands: {
  medium: number;
  high: number;
  critical: number;
}): string | null {
  if (!(bands.medium < bands.high && bands.high < bands.critical)) {
    return "Thresholds must be strictly increasing";
  }
  return null;
}

export interface ScoreReason {
  rule_id?: string;
  rule_name?: string;
  tier_label?: string;
  points: number;
  severity?: string;
  explanation?: string;
  kind?: string;
}

export interface ScoreSummary {
  raw_score: number;
  score: number;
  capped: boolean;
  severity: string;
  severity_basis?: string;
}

const ORDER: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 };

function band(score: number, thresholds: { medium: number; high: number; critical: number }): string {
  if (score >= thresholds.critical) return "critical";
  if (score >= thresholds.high) return "high";
  if (score >= thresholds.medium) return "medium";
  return "low";
}

/** Pure client-side simulation; it never mutates stored assessments. */
export function whatIfScore(
  reasons: ScoreReason[],
  thresholds: { medium: number; high: number; critical: number },
  disabledRuleIds: string[],
): { raw: number; score: number; capped: boolean; severity: string } {
  const disabled = new Set(disabledRuleIds);
  const active = reasons.filter(
    (reason) => reason.rule_id && !disabled.has(reason.rule_id) && reason.kind !== "summary",
  );
  const raw = active.reduce((total, reason) => total + reason.points, 0);
  const score = Math.min(100, Math.max(0, raw));
  const fromBand = band(score, thresholds);
  const floor = active.reduce((highest, reason) => {
    const severity = String(reason.severity ?? "low");
    return (ORDER[severity] ?? 0) > (ORDER[highest] ?? 0) ? severity : highest;
  }, "low");
  return {
    raw,
    score,
    capped: raw > 100,
    severity: (ORDER[floor] ?? 0) > (ORDER[fromBand] ?? 0) ? floor : fromBand,
  };
}

export interface TimelineLike {
  timestamp: string;
  event_type: string;
  severity: string;
  event_id?: number | null;
  summary?: string;
}

export function collapseRepeats(events: TimelineLike[]) {
  const groups: Array<{
    event_type: string;
    severity: string;
    count: number;
    first: string;
    last: string;
    ids: number[];
  }> = [];
  for (const event of events) {
    const previous = groups.at(-1);
    if (previous && previous.event_type === event.event_type && previous.severity === event.severity) {
      previous.count += 1;
      previous.last = event.timestamp;
      if (event.event_id) previous.ids.push(event.event_id);
    } else {
      groups.push({
        event_type: event.event_type,
        severity: event.severity,
        count: 1,
        first: event.timestamp,
        last: event.timestamp,
        ids: event.event_id ? [event.event_id] : [],
      });
    }
  }
  return groups;
}

export interface CollapsedEntry {
  kind: "group" | "observed" | "inferred";
  timestamp: string;
  event_type: string;
  severity: string;
  summary: string;
  count?: number;
  first?: string;
  last?: string;
  ids?: number[];
  event_id?: number | null;
  relation_to_previous?: { reason: string; strength: string; link_kind?: string } | null;
  rule_findings?: Array<{ rule_id?: string; tier_label?: string }>;
}

/** Collapse consecutive observed repeats while keeping inferred entries intact. */
export function collapseTimelineEntries(
  entries: Array<TimelineLike & { kind?: string; summary?: string }>,
): CollapsedEntry[] {
  const result: CollapsedEntry[] = [];
  for (const entry of entries) {
    if (entry.kind === "inferred") {
      result.push({
        kind: "inferred",
        timestamp: entry.timestamp,
        event_type: entry.event_type,
        severity: entry.severity,
        summary: String(entry.summary ?? entry.event_type),
      });
      continue;
    }
    const previous = result.at(-1);
    const repeatable =
      previous?.kind === "group" &&
      previous.event_type === entry.event_type &&
      previous.severity === entry.severity;
    if (repeatable && previous) {
      previous.count = (previous.count ?? 1) + 1;
      previous.last = entry.timestamp;
      if (entry.event_id) previous.ids = [...(previous.ids ?? []), entry.event_id];
      previous.summary = `×${previous.count} ${entry.event_type} between ${previous.first} and ${previous.last}`;
    } else {
      result.push({
        kind: "group",
        timestamp: entry.timestamp,
        event_type: entry.event_type,
        severity: entry.severity,
        summary: "summary" in entry ? String(entry.summary) : entry.event_type,
        count: 1,
        first: entry.timestamp,
        last: entry.timestamp,
        ids: entry.event_id ? [entry.event_id] : [],
        event_id: entry.event_id,
      });
    }
  }
  return result;
}

export function formatGap(from: string, to: string): string {
  const seconds = Math.max(0, Math.round((new Date(to).getTime() - new Date(from).getTime()) / 1000));
  if (seconds < 60) return `+${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `+${minutes}m ${remainder}s` : `+${minutes}m`;
}

export interface GraphNode {
  id: string;
  kind: string;
  value: string;
  count?: number;
}

export interface GraphEdge {
  a: string;
  b: string;
  strength: string;
  reason: string;
}

/** Deterministic circle layout; node order never changes positions. */
export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]) {
  const ordered = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const unique = ordered.filter((node, index) => index === 0 || node.id !== ordered[index - 1]!.id);
  const radius = 160;
  const centre = 200;
  const positioned = unique.map((node, index) => {
    const angle = (2 * Math.PI * index) / Math.max(1, unique.length);
    return {
      ...node,
      x: centre + radius * Math.cos(angle),
      y: centre + radius * Math.sin(angle),
    };
  });
  return { nodes: positioned, edges: [...edges].sort((a, b) => `${a.a}${a.b}`.localeCompare(`${b.a}${b.b}`)) };
}

/** Markdown-lite: only bold, inline code and safe http(s)/same-origin links. */
export function sanitizeMarkdown(input: string): string {
  const escaped = input
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const withBold = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const withCode = withBold.replace(/`([^`]+)`/g, "<code>$1</code>");
  return withCode.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, label: string, href: string) => {
    if (/^(https?:\/\/|\/)/.test(href) && !href.toLowerCase().includes("javascript:")) {
      return `<a href="${href}" rel="noopener noreferrer">${label}</a>`;
    }
    return `${label} (link removed)`;
  });
}

export const STATUS_TRANSITIONS: Record<string, string[]> = {
  open: ["investigating"],
  investigating: ["resolved", "false_positive", "closed"],
  resolved: ["investigating"],
  false_positive: ["investigating"],
  closed: ["investigating"],
  merged: [],
};

export const REASON_REQUIRED = new Set(["resolved", "false_positive"]);

export function allowedTransitions(status: string): string[] {
  return STATUS_TRANSITIONS[status] ?? [];
}

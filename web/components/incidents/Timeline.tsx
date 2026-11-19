"use client";

import { useState } from "react";

import { FactInferenceBadge } from "@/components/badges/ExplanationBadges";
import { SeverityBadge } from "@/components/badges/SeverityBadge";
import { JsonViewer } from "@/components/explain/JsonViewer";
import { formatGap } from "@/lib/incident/helpers";

export interface TimelineEntryData {
  timestamp: string;
  event_id?: number | null;
  event_type: string;
  severity: string;
  summary: string;
  kind?: string;
  relation_to_previous?: { reason: string; strength: string; link_kind?: string } | null;
  rule_findings?: Array<{ rule_id?: string; tier_label?: string }>;
  evidence_event_ids?: number[];
  raw?: unknown;
  count?: number;
  first?: string;
  last?: string;
  ids?: number[];
  members?: TimelineEntryData[];
}

export function RelationConnector({ reason, strength }: { reason: string; strength: string }) {
  const weak = strength !== "strong";
  return (
    <div
      data-testid={`relation-${weak ? "weak" : "strong"}`}
      className={`ml-4 border-l-2 py-1 pl-4 text-xs text-slate-500 ${weak ? "border-dashed" : "border-solid"}`}
    >
      {weak ? "Weak: " : "Strong: "}
      {reason}
    </div>
  );
}

function collapse(entries: TimelineEntryData[]): TimelineEntryData[] {
  const result: TimelineEntryData[] = [];
  for (const entry of entries) {
    const previous = result.at(-1);
    const repeatable =
      entry.kind !== "inferred" &&
      previous?.kind === "group" &&
      previous.event_type === entry.event_type &&
      previous.severity === entry.severity;
    if (repeatable && previous) {
      const count = (previous.count ?? 1) + 1;
      previous.count = count;
      previous.last = entry.timestamp;
      previous.ids = [...(previous.ids ?? []), ...(entry.event_id ? [entry.event_id] : [])];
      previous.members = [...(previous.members ?? []), entry];
      previous.summary = `×${count} ${entry.event_type} between ${previous.first} and ${entry.timestamp}`;
    } else {
      result.push({
        ...entry,
        kind: entry.kind === "inferred" ? "inferred" : "group",
        count: entry.kind === "inferred" ? undefined : 1,
        first: entry.timestamp,
        last: entry.timestamp,
        ids: entry.event_id ? [entry.event_id] : [],
        members: entry.kind === "inferred" ? undefined : [entry],
      });
    }
  }
  return result;
}

export function Timeline({
  entries,
  collapsed = false,
  highlightedEvidence = [],
}: {
  entries: TimelineEntryData[];
  collapsed?: boolean;
  highlightedEvidence?: number[];
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [showAll, setShowAll] = useState(false);
  const [hoveredEvidence, setHoveredEvidence] = useState<number[]>([]);
  const ordered = [...entries].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const prepared = collapsed ? collapse(ordered) : ordered;
  const visible = showAll ? prepared : prepared.slice(0, 2000);
  const gaps = visible.map((entry, index) =>
    index === 0 ? "" : formatGap(visible[index - 1]!.timestamp, entry.timestamp),
  );
  const highlighted = new Set([...highlightedEvidence, ...hoveredEvidence]);

  return (
    <div>
      <ul aria-label="Incident timeline" className="space-y-1">
        {visible.map((entry, index) => {
          const gap = gaps[index] ?? "";
          const inferred = entry.kind === "inferred";
          const isGroup = entry.kind === "group" && (entry.count ?? 1) > 1;
          const cited = entry.evidence_event_ids ?? [];
          const ownIds = entry.ids ?? (entry.event_id ? [entry.event_id] : []);
          const isCited = ownIds.some((value) => highlighted.has(value));
          return (
            <li
              key={`${entry.timestamp}-${entry.event_id ?? index}`}
              id={entry.event_id ? `event-${entry.event_id}` : undefined}
              data-highlighted={isCited ? "true" : undefined}
              className={isCited ? "bg-blue-50 dark:bg-blue-950" : undefined}
              onMouseEnter={() => {
                if (inferred && cited.length) setHoveredEvidence(cited);
              }}
              onMouseLeave={() => setHoveredEvidence([])}
            >
              {entry.relation_to_previous ? (
                <RelationConnector
                  reason={entry.relation_to_previous.reason}
                  strength={entry.relation_to_previous.strength}
                />
              ) : null}
              <div className="rounded border border-slate-200 p-2 dark:border-slate-700">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="tabular-nums text-slate-500">
                    {entry.timestamp} {gap ? <span aria-label="gap to previous">{gap}</span> : null}
                  </span>
                  <SeverityBadge severity={entry.severity} />
                  <FactInferenceBadge kind={inferred ? "inference" : "fact"} />
                  <span className="font-medium">{entry.event_type}</span>
                </div>
                <p className="mt-1 text-sm">{entry.summary}</p>
                {isGroup ? (
                  <button
                    type="button"
                    className="mt-1 text-xs underline"
                    onClick={() =>
                      setExpanded((current) => {
                        const next = new Set(current);
                        if (next.has(index)) next.delete(index);
                        else next.add(index);
                        return next;
                      })
                    }
                  >
                    {expanded.has(index) ? "Hide" : "Expand"} {entry.count} events
                  </button>
                ) : null}
                {isGroup && expanded.has(index) && entry.members ? (
                  <ul className="mt-1 space-y-1 border-l-2 border-slate-200 pl-3 text-xs dark:border-slate-700">
                    {entry.members.map((member, memberIndex) => (
                      <li key={`${member.timestamp}-${memberIndex}`}>
                        <span className="tabular-nums text-slate-500">{member.timestamp}</span>{" "}
                        {member.summary}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {entry.rule_findings?.length ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Rule: {entry.rule_findings.map((item) => `${item.rule_id ?? "?"} (${item.tier_label ?? "?"})`).join(", ")}
                  </p>
                ) : null}
                {cited.length ? (
                  <p className="mt-1 text-xs text-slate-500">Cites events: {cited.join(", ")}</p>
                ) : null}
                {entry.raw !== undefined ? (
                  <div className="mt-1">
                    <button
                      type="button"
                      className="text-xs underline"
                      onClick={() =>
                        setExpanded((current) => {
                          const next = new Set(current);
                          if (next.has(index)) next.delete(index);
                          else next.add(index);
                          return next;
                        })
                      }
                    >
                      {expanded.has(index) ? "Hide" : "Show"} raw event JSON
                    </button>
                    {expanded.has(index) ? <JsonViewer value={entry.raw} /> : null}
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
      {prepared.length > 2000 && !showAll ? (
        <button type="button" className="mt-2 text-sm underline" onClick={() => setShowAll(true)}>
          Show all {prepared.length} entries
        </button>
      ) : null}
    </div>
  );
}

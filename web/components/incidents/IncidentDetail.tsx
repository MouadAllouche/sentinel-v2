"use client";

import { useEffect, useMemo, useState } from "react";

import { IncidentHeader } from "@/components/incidents/IncidentHeader";
import { MergedBanner } from "@/components/incidents/MergedBanner";
import { EntityGraph } from "@/components/incidents/EntityGraph";
import { ExplanationPanel } from "@/components/incidents/ExplanationPanel";
import { NotesPanel } from "@/components/incidents/NotesPanel";
import { ScoreReasonsTable } from "@/components/incidents/ScoreReasonsTable";
import { StatusHistory } from "@/components/incidents/StatusHistory";
import { Timeline, type TimelineEntryData } from "@/components/incidents/Timeline";
import { WhatIfPanel } from "@/components/incidents/WhatIfPanel";
import { Button, Card, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { ApiError } from "@/lib/api/client";
import {
  useAddIncidentNote,
  useApiList,
  useIncident,
  useIncidentEvents,
  useIncidentExplanation,
  useIncidentGraph,
  useIncidentHistory,
  useIncidentNotes,
  useIncidentStatusMutation,
  useIncidentTimeline,
  useRiskThresholds,
  useSetAssignee,
} from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";
import type { ScoreReason, ScoreSummary } from "@/lib/incident/helpers";
import { collapseRepeats } from "@/lib/incident/helpers";

const TABS = ["timeline", "evidence", "why-grouped", "why-score", "graph", "notes", "history"] as const;
type Tab = (typeof TABS)[number];

function currentTab(): Tab {
  if (typeof window === "undefined") return "timeline";
  const hash = window.location.hash.replace("#", "");
  return (TABS as readonly string[]).includes(hash) ? (hash as Tab) : "timeline";
}

export function IncidentDetail({ id }: { id: number }) {
  const me = useMe();
  const { show } = useToast();
  const [tab, setTab] = useState<Tab>(currentTab);
  const [hideWeak, setHideWeak] = useState(false);
  const [observedOnly, setObservedOnly] = useState(false);
  const [collapsed, setCollapsed] = useState(true);
  const [eventCursor, setEventCursor] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const incident = useIncident(id);
  const timeline = useIncidentTimeline(id);
  const explanation = useIncidentExplanation(id);
  const graph = useIncidentGraph(id);
  const notes = useIncidentNotes(id);
  const history = useIncidentHistory(id);
  const events = useIncidentEvents(id, eventCursor);
  const allFindings = useApiList<Record<string, unknown>>("/api/rules/findings");
  const thresholds = useRiskThresholds();
  const statusMutation = useIncidentStatusMutation(id);
  const noteMutation = useAddIncidentNote(id);
  const assigneeMutation = useSetAssignee(id);

  useEffect(() => {
    const onHashChange = () => setTab(currentTab());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const eventMap = useMemo(
    () => new Map((events.data?.items ?? []).map((event) => [event.id, event])),
    [events.data],
  );

  if (incident.isLoading) return <Skeleton rows={6} />;
  if (!incident.data) return <ErrorState message="Could not load this incident." />;

  const record = incident.data;
  const incidentEventIds = new Set(record.event_ids ?? []);
  const incidentFindings = (allFindings.data?.items ?? []).filter((finding) => {
    let evidence: number[] = [];
    if (Array.isArray(finding.evidence_event_ids)) evidence = finding.evidence_event_ids as number[];
    else if (typeof finding.evidence_event_ids_json === "string") {
      try {
        evidence = JSON.parse(finding.evidence_event_ids_json) as number[];
      } catch {
        evidence = [];
      }
    }
    return evidence.some((value) => incidentEventIds.has(value));
  });
  const reasons = ((record.assessment as { reasons?: ScoreReason[] } | undefined)?.reasons ?? []) as ScoreReason[];
  const summary = reasons.find((reason) => reason.kind === "summary") as unknown as ScoreSummary | undefined;
  let entries: TimelineEntryData[] = (timeline.data ?? []) as TimelineEntryData[];
  if (observedOnly) entries = entries.filter((entry) => entry.kind === "observed");
  if (hideWeak) {
    entries = entries.filter((entry) => entry.relation_to_previous?.strength !== "weak");
  }
  const repeatGroups = collapseRepeats(
    entries.filter((entry) => entry.kind === "observed").map((entry) => ({
      timestamp: entry.timestamp,
      event_type: entry.event_type,
      severity: entry.severity,
      event_id: entry.event_id,
    })),
  );
  const repeated = repeatGroups.filter((group) => group.count > 1).length;
  entries = entries.map((entry) => ({ ...entry, raw: entry.event_id ? eventMap.get(entry.event_id) : undefined }));

  const selectTab = (next: Tab) => {
    setTab(next);
    window.history.replaceState(null, "", `${window.location.pathname}#${next}`);
  };

  return (
    <div className="space-y-4">
      <IncidentHeader
        incident={{
          id: id,
          title: record.title ?? `Incident #${id}`,
          severity: record.severity,
          status: record.status,
          risk_score: record.score ?? record.risk_score ?? 0,
          first_seen: record.first_seen,
          last_seen: record.last_seen,
          assignee: record.assignee,
          mitre: record.mitre,
        }}
        currentRole={me.role}
        onAssigneeChange={(assignee) => {
          void assigneeMutation.mutateAsync(assignee).catch(() => show("Could not update the assignee"));
        }}
        error={statusError}
        onStatusChange={(status, reason) => {
          void statusMutation
            .mutateAsync({
              status,
              reason,
              updatedAt: String(record.updated_at ?? ""),
            })
            .then(() => {
              setStatusError(null);
              show(`Status changed to ${status}`, "success");
            })
            .catch((cause: unknown) => {
              if (cause instanceof ApiError && cause.status === 409) {
                setStatusError("conflict");
              } else {
                setStatusError(null);
                show("Could not change the status");
              }
            });
        }}
      />
      {record.status === "merged" && record.merged_into ? (
        <MergedBanner targetId={Number(record.merged_into)} />
      ) : null}

      <div className="flex flex-wrap gap-2">
        {TABS.map((item) => (
          <button
            key={item}
            type="button"
            aria-current={tab === item ? "page" : undefined}
            onClick={() => selectTab(item)}
            className={`rounded px-3 py-1 text-sm ${tab === item ? "bg-slate-900 text-white" : "border border-slate-300 dark:border-slate-600"}`}
          >
            {item.replaceAll("-", " ")}
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <div className="space-y-3 lg:col-span-3">
          {tab === "timeline" ? (
            <Card>
              <div className="mb-2 flex flex-wrap gap-3 text-sm">
                <label className="inline-flex items-center gap-1">
                  <input type="checkbox" checked={hideWeak} onChange={(e) => setHideWeak(e.target.checked)} />
                  Hide weak links
                </label>
                <label className="inline-flex items-center gap-1">
                  <input type="checkbox" checked={observedOnly} onChange={(e) => setObservedOnly(e.target.checked)} />
                  Only observed
                </label>
                <label className="inline-flex items-center gap-1">
                  <input type="checkbox" checked={collapsed} onChange={(e) => setCollapsed(e.target.checked)} />
                  Collapse repeats
                </label>
              </div>
              {collapsed && repeated > 0 ? (
                <p className="mb-2 text-xs text-slate-500">
                  {repeated} repeated runs collapsed; expand them in the timeline.
                </p>
              ) : null}
              {timeline.isLoading ? (
                <Skeleton rows={5} />
              ) : (
                <Timeline entries={entries} collapsed={collapsed} />
              )}
            </Card>
          ) : null}
          {tab === "evidence" ? (
            <Card>
              <h2 className="mb-2 text-lg font-semibold">Evidence</h2>
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Incident evidence events</caption>
                <thead><tr><th scope="col">Time</th><th scope="col">Type</th><th scope="col">Summary</th><th scope="col">Context</th></tr></thead>
                <tbody>
                  {(events.data?.items ?? []).map((event) => (
                    <tr key={event.id} className="border-b border-slate-100 dark:border-slate-800">
                      <td>{event.timestamp}</td>
                      <td>{event.event_type}</td>
                      <td>{event.description}</td>
                      <td>
                        <a className="mr-2 text-blue-700 underline dark:text-blue-300" href={`/events?incident_id=${id}#event-${event.id}`}>
                          Open event
                        </a>
                        <a className="mr-2 text-blue-700 underline dark:text-blue-300" href={`/events?source_ip=${encodeURIComponent(String(event.source_ip ?? ""))}`}>
                          Show from this IP
                        </a>
                        {me.role === "admin" && event.source_ip ? (
                          <a className="text-blue-700 underline dark:text-blue-300" href={`/allowlist?value=${encodeURIComponent(String(event.source_ip))}`}>
                            Add allowlist
                          </a>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h3 className="mt-4 font-semibold">Rule findings</h3>
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Rule findings contributing to this incident</caption>
                <thead><tr><th scope="col">Rule</th><th scope="col">Tier</th><th scope="col">Severity</th><th scope="col">Evidence</th></tr></thead>
                <tbody>
                  {incidentFindings.length === 0 ? (
                    <tr><td colSpan={4}>No rule findings reference this incident.</td></tr>
                  ) : (
                    incidentFindings.map((finding, index) => (
                      <tr key={`${String(finding.rule_id)}-${index}`} className="border-b border-slate-100 dark:border-slate-800">
                        <td>{String(finding.rule_id ?? "unknown")}</td>
                        <td>{String(finding.tier_label ?? "?")}</td>
                        <td>{String(finding.severity ?? "—")}</td>
                        <td>
                          {(Array.isArray(finding.evidence_event_ids) ? finding.evidence_event_ids as number[] : [])
                            .map((value) => <a key={value} className="mr-1 text-blue-700 underline dark:text-blue-300" href={`/events?incident_id=${id}#event-${value}`}>#{value}</a>)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
              <div className="mt-2 flex gap-2">
                <Button disabled={!eventCursor} onClick={() => setEventCursor(null)}>Previous page</Button>
                <Button disabled={!events.data?.next_cursor} onClick={() => setEventCursor(events.data?.next_cursor ?? null)}>Next page</Button>
              </div>
            </Card>
          ) : null}
          {tab === "why-grouped" ? (
            <Card>
              <h2 className="mb-2 text-lg font-semibold">Why these events were grouped</h2>
              {explanation.isLoading ? <Skeleton rows={4} /> : <ExplanationPanel explanation={explanation.data ?? {}} />}
            </Card>
          ) : null}
          {tab === "why-score" ? (
            <div className="space-y-3">
              <Card>
                <h2 className="mb-2 text-lg font-semibold">Why this score</h2>
                <ScoreReasonsTable reasons={reasons} summary={summary ?? null} />
              </Card>
              <Card>
                <WhatIfPanel reasons={reasons} thresholds={thresholds.data} />
              </Card>
            </div>
          ) : null}
          {tab === "graph" ? (
            <Card>
              <h2 className="mb-2 text-lg font-semibold">Entities and relationships</h2>
              <EntityGraph
                nodes={graph.data?.nodes ?? []}
                edges={graph.data?.edges ?? []}
              />
            </Card>
          ) : null}
          {tab === "notes" ? (
            <Card>
              <h2 className="mb-2 text-lg font-semibold">Analyst notes</h2>
              <NotesPanel
                notes={notes.data ?? []}
                currentRole={me.role}
                onAdd={(body) => {
                  void noteMutation.mutateAsync(body).catch(() => show("Could not add the note"));
                }}
              />
            </Card>
          ) : null}
          {tab === "history" ? (
            <Card>
              <h2 className="mb-2 text-lg font-semibold">Status history</h2>
              <StatusHistory
                entries={(history.data?.history ?? []) as Array<{
                  id: number;
                  from_status: string;
                  to_status: string;
                  actor: string;
                  reason?: string | null;
                  at: string;
                }>}
                audit={(history.data?.audit ?? []) as Array<{ id: number; actor: string; action: string; ts: string }>}
              />
            </Card>
          ) : null}
        </div>

        <aside aria-label="Incident quick actions" className="space-y-3 lg:sticky lg:top-4 lg:col-span-1">
          <Card>
            <h2 className="font-semibold">Key facts</h2>
            <dl className="mt-2 space-y-1 text-sm">
              <div><dt className="inline font-medium">Primary IP:</dt> <dd className="inline">{record.primary_ip ?? "—"}</dd></div>
              <div><dt className="inline font-medium">Username:</dt> <dd className="inline">{record.primary_username ?? "—"}</dd></div>
              <div><dt className="inline font-medium">Events:</dt> <dd className="inline">{record.event_ids?.length ?? 0}</dd></div>
              <div><dt className="inline font-medium">Duration:</dt> <dd className="inline">{record.first_seen && record.last_seen ? `${record.first_seen} → ${record.last_seen}` : "—"}</dd></div>
            </dl>
          </Card>
          <Card>
            <h2 className="font-semibold">Quick actions</h2>
            <div className="mt-2 flex flex-wrap gap-2 text-sm">
              <a className="text-blue-700 underline dark:text-blue-300" href={`/api/incidents/${id}/export?format=md`} download>Copy Markdown</a>
              <a className="text-blue-700 underline dark:text-blue-300" href={`/api/incidents/${id}/export?format=json`} download>Copy JSON</a>
              <a className="text-blue-700 underline dark:text-blue-300" href={`/api/incidents/${id}/export?format=pdf`} download>Export PDF</a>
              <Button onClick={() => void navigator.clipboard?.writeText(window.location.href)}>Copy link</Button>
              <Button
                onClick={() => {
                  const text = `${record.title ?? "Incident"} — ${record.severity}, score ${record.score ?? record.risk_score ?? 0}. ${record.summary ?? ""}`.trim();
                  void navigator.clipboard?.writeText(text);
                }}
              >
                Copy summary
              </Button>
            </div>
          </Card>
          <Card>
            <h2 className="font-semibold">Grouping caveat</h2>
            <p className="mt-1 text-xs text-slate-500">
              Inferred statements cite observed entries; weak links are listed on the “Why grouped” tab.
            </p>
          </Card>
        </aside>
      </div>
    </div>
  );
}

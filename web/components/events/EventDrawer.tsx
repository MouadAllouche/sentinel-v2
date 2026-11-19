"use client";

import Link from "next/link";
import { useState } from "react";

import { FactInferenceBadge } from "@/components/badges/ExplanationBadges";
import { JsonViewer } from "@/components/explain/JsonViewer";
import { RequireRole, type Role } from "@/lib/auth";
import { Button, Input, Label } from "@/components/ui/primitives";
import { useAddAllowlistEntry } from "@/lib/api/hooks";
import { severitySourceText, type EventLike } from "@/lib/events";
import { useToast } from "@/components/ui/Toaster";

export function EventDrawer({
  event,
  onClose,
  roleOfUser,
  findings = [],
  incidents = [],
}: {
  event: EventLike | null;
  onClose: () => void;
  roleOfUser?: Role;
  findings?: Array<{ rule_id?: string; tier_label?: string }>;
  incidents?: Array<{ id: number }>;
}) {
  const [allowlistOpen, setAllowlistOpen] = useState(false);
  const [reason, setReason] = useState("");
  const addEntry = useAddAllowlistEntry();
  const { show } = useToast();

  if (!event) return null;

  return (
    <aside
      role="dialog"
      aria-modal="true"
      aria-label={`Event ${event.id} details`}
      className="fixed inset-y-0 right-0 z-40 w-full max-w-lg overflow-y-auto border-l border-slate-200 bg-white p-4 shadow-xl dark:border-slate-700 dark:bg-slate-900"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Event #{event.id}</h2>
          <p className="text-sm text-slate-600 dark:text-slate-300">{event.description}</p>
        </div>
        <Button onClick={onClose} aria-label="Close details">Close</Button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <FactInferenceBadge kind="fact" />
        <span className="text-xs">Severity source:</span>
        <span data-testid="severity-source">{severitySourceText(event)}</span>
        <Link href="/severity" className="text-sm text-blue-700 underline dark:text-blue-300">
          Severity settings
        </Link>
      </div>

      <section className="mt-4">
        <h3 className="font-semibold">Normalized event</h3>
        <JsonViewer value={event} />
      </section>

      {event.enrichment ? (
        <section className="mt-4">
          <h3 className="font-semibold">Enrichment</h3>
          <dl className="mt-1 text-sm">
            {Object.entries(event.enrichment).map(([key, value]) => (
              <div key={key} className="flex gap-2">
                <dt className="font-medium">{key}:</dt>
                <dd>{JSON.stringify(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <section className="mt-4">
        <h3 className="font-semibold">Related findings and incidents</h3>
        {findings.length === 0 && incidents.length === 0 ? (
          <p className="mt-1 text-sm text-slate-500">No related findings or incidents.</p>
        ) : (
          <ul className="mt-1 space-y-1 text-sm">
            {findings.map((finding, index) => (
              <li key={index}>
                Rule {finding.rule_id ?? "unknown"} · tier {finding.tier_label ?? "unknown"}
              </li>
            ))}
            {incidents.map((incident) => (
              <li key={incident.id}>
                <Link className="text-blue-700 underline dark:text-blue-300" href={`/incidents/${incident.id}`}>
                  Incident #{incident.id}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-4 space-y-2">
        <h3 className="font-semibold">Context actions</h3>
        <Link
          className="block text-sm text-blue-700 underline dark:text-blue-300"
          href={`/events?source_ip=${encodeURIComponent(String(event.source_ip ?? ""))}`}
        >
          Show events from this IP
        </Link>
        <Link
          className="block text-sm text-blue-700 underline dark:text-blue-300"
          href={`/events?username=${encodeURIComponent(String(event.username ?? ""))}`}
        >
          Show events for this user
        </Link>
        <RequireRole requiredRole="admin" roleOfUser={roleOfUser}>
          <Button onClick={() => setAllowlistOpen(true)}>Add allowlist entry…</Button>
          <Link
            className="ml-2 inline-block text-sm text-blue-700 underline dark:text-blue-300"
            href={`/rules/new?template=${encodeURIComponent(event.event_type)}`}
          >
            Create rule from this event…
          </Link>
        </RequireRole>
      </section>

      {allowlistOpen ? (
        <div role="dialog" aria-modal="true" aria-label="Add allowlist entry" className="mt-4 rounded border border-slate-300 p-3">
          <Label htmlFor="allowlist-reason">Reason</Label>
          <Input
            id="allowlist-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Why this value is expected"
          />
          <div className="mt-2 flex gap-2">
            <Button onClick={() => setAllowlistOpen(false)}>Cancel</Button>
            <Button
              disabled={reason.trim().length < 5}
              onClick={() => {
                void addEntry
                  .mutateAsync({
                    kind: "ip",
                    value: String(event.source_ip ?? ""),
                    scope: "suppress_alerts",
                    reason,
                  })
                  .then(() => {
                    show("Allowlist entry added", "success");
                    setAllowlistOpen(false);
                  })
                  .catch(() => show("Could not add the allowlist entry"));
              }}
            >
              Confirm
            </Button>
          </div>
        </div>
      ) : null}
    </aside>
  );
}

"use client";

import { Button } from "@/components/ui/primitives";
import type { EventFilters } from "@/lib/filters";

export function EventExport({ filters }: { filters: EventFilters }) {
  const params = new URLSearchParams();
  for (const value of filters.event_type) params.append("event_type", value);
  for (const value of filters.severity) params.append("severity", value);
  for (const value of filters.source) params.append("source", value);
  if (filters.username) params.set("username", filters.username);
  if (filters.source_ip) params.set("source_ip", filters.source_ip);
  if (filters.source_cidr) params.set("source_cidr", filters.source_cidr);
  if (filters.process_name) params.set("process_name", filters.process_name);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  if (filters.search) params.set("search", filters.search);
  // `allowlisted: true` means "include allowlisted"; the API only understands the
  // explicit false case, which excludes them. Match the table's semantics exactly.
  if (filters.allowlisted === false) params.set("allowlisted", "false");
  if (filters.in_incident !== null) params.set("in_incident", String(filters.in_incident));
  if (filters.incident_id !== null) params.set("incident_id", String(filters.incident_id));

  const download = (format: "csv" | "json") => {
    const anchor = document.createElement("a");
    anchor.href = `/api/events/export?format=${format}&${params.toString()}`;
    anchor.download = `sentinel-events.${format}`;
    anchor.click();
  };

  return (
    <section aria-label="Export events" className="flex flex-wrap items-center gap-2 text-sm">
      <Button onClick={() => download("csv")} aria-label="Export CSV">Export CSV</Button>
      <Button onClick={() => download("json")} aria-label="Export JSON">Export JSON</Button>
      <span className="text-xs text-slate-500">The server caps exports at 100 000 rows.</span>
    </section>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";

import { EventDrawer } from "@/components/events/EventDrawer";
import { EventExport } from "@/components/events/EventExport";
import { EventTable } from "@/components/events/EventTable";
import { FilterBar } from "@/components/events/FilterBar";
import { NewEventsBanner } from "@/components/events/NewEventsBanner";
import { QuickStats } from "@/components/events/QuickStats";
import { SavedFilters } from "@/components/events/SavedFilters";
import { Button, Card, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import {
  useApiList,
  useCreateSavedFilter,
  useDeleteSavedFilter,
  useEvent,
  useEvents,
  useFindings,
  useIncidents,
  useSavedFilters,
} from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";
import { type EventFilters, emptyFilters, filtersToSearch, parseEventFilters } from "@/lib/filters";
import type { EventLike } from "@/lib/events";

function apiFilters(filters: EventFilters, cursor: string | null): Record<string, unknown> {
  const result: Record<string, unknown> = {
    event_type: filters.event_type,
    severity: filters.severity,
    source: filters.source,
    limit: filters.limit,
  };
  for (const key of [
    "username", "source_ip", "source_cidr", "process_name", "since", "until", "search",
  ] as const) {
    if (filters[key]) result[key] = filters[key];
  }
  if (filters.allowlisted === false) result.allowlisted = false;
  if (filters.in_incident !== null) result.in_incident = filters.in_incident;
  if (filters.incident_id !== null) result.incident_id = filters.incident_id;
  if (cursor) result.cursor = cursor;
  return result;
}

export function EventsExplorer() {
  const [filters, setFilters] = useState<EventFilters>(() =>
    typeof window === "undefined"
      ? emptyFilters
      : parseEventFilters(window.location.search, new Date().toISOString()),
  );
  const [cursors, setCursors] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [live, setLive] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const [debounced, setDebounced] = useState(filters);
  const seen = useRef<Set<number>>(new Set());
  const me = useMe();
  const { show } = useToast();
  const cursor = cursors.at(-1) ?? null;
  const query = useEvents(apiFilters(debounced, cursor), {
    refetchInterval: live ? 10_000 : undefined,
  });
  const detail = useEvent(selectedId ?? 0);
  const findings = useFindings();
  const incidents = useIncidents();
  const saved = useSavedFilters();
  const createSaved = useCreateSavedFilter();
  const deleteSaved = useDeleteSavedFilter();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(filters), 250);
    return () => clearTimeout(timer);
  }, [filters]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const search = filtersToSearch(filters);
    window.history.replaceState(null, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
  }, [filters]);

  useEffect(() => {
    const items = (query.data?.items ?? []) as EventLike[];
    if (!items.length) return;
    const fresh = items.filter((item) => !seen.current.has(item.id));
    for (const item of items) seen.current.add(item.id);
    if (fresh.length && live && window.scrollY > 200) setNewCount((count) => count + fresh.length);
  }, [query.data, live]);

  const changeFilters = (next: EventFilters) => {
    setCursors([]);
    setFilters(next);
  };
  const saveCurrent = () => {
    const name = window.prompt("Filter name");
    if (!name) return;
    void createSaved
      .mutateAsync({ name, page: "events", query: filters as unknown as Record<string, unknown> })
      .then(() => show("Filter saved", "success"))
      .catch(() => show("Could not save the filter"));
  };
  const selectedEvent = (detail.data as EventLike | undefined) ?? null;
  const relatedFindings = (findings.data ?? []).filter((item) =>
    String(item.evidence_event_ids_json ?? "").includes(String(selectedId)),
  );
  const relatedIncidents = (incidents.data ?? []).filter((item) =>
    Array.isArray(item.event_ids) && (item.event_ids as number[]).includes(selectedId ?? -1),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Events</h1>
        <div className="flex gap-2">
          <Button onClick={() => setLive((value) => !value)} aria-pressed={live}>
            {live ? "Live mode: on" : "Live mode: off"}
          </Button>
          <Button onClick={saveCurrent}>Save filter</Button>
        </div>
      </div>
      <FilterBar filters={filters} onChange={changeFilters} />
      <SavedFilters
        saved={saved.data ?? []}
        onApply={(stored) => changeFilters({ ...emptyFilters, ...(stored as Partial<EventFilters>) })}
        onSave={saveCurrent}
        onDelete={(identifier) => void deleteSaved.mutateAsync(identifier)}
      />
      <NewEventsBanner
        count={newCount}
        onLoad={() => {
          setNewCount(0);
          void query.refetch();
        }}
      />
      <QuickStats
        events={(query.data?.items ?? []) as EventLike[]}
        total={query.data?.total}
        onBrush={(since, until) => changeFilters({ ...filters, since, until, preset: "custom" })}
      />
      <EventExport filters={filters} />
      <Card>
        {query.isLoading ? (
          <Skeleton rows={5} />
        ) : query.isError ? (
          <ErrorState message="Could not load events." onRetry={() => void query.refetch()} />
        ) : (
          <EventTable
            events={(query.data?.items ?? []) as EventLike[]}
            filters={filters}
            onFiltersChange={changeFilters}
            onSelect={(event) => setSelectedId(event.id)}
            selectedId={selectedId}
            nextCursor={query.data?.next_cursor ?? null}
            onPage={(next) => setCursors((stack) => [...stack, next])}
            onPrevious={() => setCursors((stack) => stack.slice(0, -1))}
          />
        )}
      </Card>
      {selectedId ? (
        <EventDrawer
          event={selectedEvent}
          onClose={() => setSelectedId(null)}
          roleOfUser={me.role}
          findings={relatedFindings}
          incidents={relatedIncidents}
        />
      ) : null}
    </div>
  );
}

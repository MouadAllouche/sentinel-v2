"use client";

import { useCallback, useState } from "react";

import { IncidentList } from "@/components/incidents/IncidentList";
import { Card, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { useBulkIncidentStatus, useIncidentPage } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";
import { type IncidentFilters, parseIncidentFilters } from "@/lib/incident/filters";
import { useLiveUpdates } from "@/lib/sse";

export function IncidentListRoute() {
  const [filters, setFilters] = useState<IncidentFilters>(() =>
    typeof window === "undefined"
      ? { status: [], severity: [], assignee: "", search: "", since: "", until: "", needsAttention: false, sort: "risk", cursor: null }
      : parseIncidentFilters(window.location.search),
  );
  const [cursors, setCursors] = useState<string[]>([]);
  const [highlighted, setHighlighted] = useState<Set<number>>(new Set());
  const onMessage = useCallback((message: { type: string; id?: number | string }) => {
    if (!String(message.type).includes("incident") || typeof message.id !== "number") return;
    setHighlighted((current) => new Set(current).add(message.id as number));
    setTimeout(() => setHighlighted((current) => {
      const next = new Set(current);
      next.delete(message.id as number);
      return next;
    }), 3000);
  }, []);
  useLiveUpdates({ onMessage });
  const me = useMe();
  const { show } = useToast();
  const cursor = cursors.at(-1) ?? null;
  const query = useIncidentPage({ ...filters, cursor: null }, cursor);
  const bulk = useBulkIncidentStatus();

  return (
    <Card>
      {query.isLoading ? (
        <Skeleton rows={6} />
      ) : query.isError ? (
        <ErrorState message="Could not load incidents." onRetry={() => void query.refetch()} />
      ) : (
        <IncidentList
          incidents={query.data?.items ?? []}
          filters={filters}
          onFiltersChange={(next) => {
            setCursors([]);
            setFilters({ ...next, cursor: null });
          }}
          onBulkStatus={(ids, status, reason) => {
            void bulk
              .mutateAsync({ ids, status, reason })
              .then(() => show(`Updated ${ids.length} incidents`, "success"))
              .catch(() => show("Could not update the incidents"));
          }}
          currentRole={me.role}
          highlightedIds={highlighted}
          nextCursor={query.data?.next_cursor ?? null}
          onPage={(next) => setCursors((stack) => [...stack, next])}
          onPrevious={() => setCursors((stack) => stack.slice(0, -1))}
        />
      )}
    </Card>
  );
}

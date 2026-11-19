"use client";

import { useState } from "react";

import { AuditPage, type AuditFilters, type AuditRow } from "@/components/audit/AuditPage";
import { Button, ErrorState, Skeleton } from "@/components/ui/primitives";
import { client } from "@/lib/api/client";
import { useApiList } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";

const initial: AuditFilters = { actor: "", action: "", targetType: "", since: "", until: "" };

export function AuditRoute() {
  const [filters, setFilters] = useState<AuditFilters>(initial);
  const [cursor, setCursor] = useState<string | null>(null);
  const me = useMe();
  const query = useApiList<AuditRow>("/api/audit", {
    ...(filters.actor ? { actor: filters.actor } : {}),
    ...(filters.action ? { action_prefix: filters.action } : {}),
    ...(filters.targetType ? { target_type: filters.targetType } : {}),
    ...(filters.since ? { since: filters.since } : {}),
    ...(filters.until ? { until: filters.until } : {}),
    ...(cursor ? { cursor } : {}),
  });

  if (query.isLoading) return <Skeleton rows={4} />;
  if (query.isError) return <ErrorState message="Could not load the audit log." />;
  return (
    <div className="space-y-2">
      <AuditPage
        rows={query.data?.items ?? []}
        filters={filters}
        onFiltersChange={(next) => {
          setCursor(null);
          setFilters(next);
        }}
        onExport={() => {
          const safe = (value: unknown) => {
            const text = String(value ?? "");
            return `"${(/^[=+\-@]/.test(text) ? `'${text}` : text).replaceAll('"', '""')}"`;
          };
          const lines = [["ts", "actor", "action", "target_type", "target_id"].join(",")];
          for (const row of query.data?.items ?? []) {
            lines.push([row.ts, row.actor, row.action, row.target_type, row.target_id].map(safe).join(","));
          }
          const blob = new Blob([lines.join("\n")], { type: "text/csv" });
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement("a");
          anchor.href = url;
          anchor.download = "sentinel-audit.csv";
          anchor.click();
          URL.revokeObjectURL(url);
        }}
        role={me.role}
      />
      <div className="flex gap-2">
        <Button disabled={!cursor} onClick={() => setCursor(null)}>First page</Button>
        <Button disabled={!query.data?.next_cursor} onClick={() => setCursor(query.data?.next_cursor ?? null)}>
          Next page
        </Button>
      </div>
    </div>
  );
}

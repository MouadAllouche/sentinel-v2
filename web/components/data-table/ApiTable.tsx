"use client";

import { useState } from "react";

import { Card, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useApiList } from "@/lib/api/hooks";
import type { paths } from "@/lib/api/schema";

import { DataTable } from "./DataTable";

export function ApiTable<T extends Record<string, unknown>>({
  path,
  columns,
  title,
  filters = {},
}: {
  path: keyof paths;
  columns: ReadonlyArray<keyof T & string>;
  title: string;
  filters?: Record<string, unknown>;
}) {
  const [cursors, setCursors] = useState<string[]>([]);
  const cursor = cursors.at(-1) ?? null;
  const query = useApiList<T>(path, { ...filters, ...(cursor ? { cursor } : {}) });

  return (
    <Card>
      <h2 className="mb-3 text-lg font-semibold">{title}</h2>
      {query.isLoading ? (
        <Skeleton />
      ) : query.isError ? (
        <ErrorState message="Could not load this list." onRetry={() => void query.refetch()} />
      ) : (
        <DataTable
          rows={query.data?.items ?? []}
          columns={columns}
          cursor={cursors.length > 1 ? (cursors.at(-2) ?? null) : null}
          nextCursor={query.data?.next_cursor ?? null}
          onPage={(next) => setCursors((stack) => [...stack, next])}
          onPrevious={() => setCursors((stack) => stack.slice(0, -1))}
          title={title}
        />
      )}
      {cursors.length > 0 ? (
        <button
          type="button"
          className="mt-2 text-sm underline"
          onClick={() => setCursors((stack) => stack.slice(0, -1))}
        >
          Back to first page
        </button>
      ) : null}
    </Card>
  );
}

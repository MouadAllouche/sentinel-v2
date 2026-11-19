"use client";

import {
  columnFilteringFeature,
  createFilteredRowModel,
  filterFns,
  flexRender,
  globalFilteringFeature,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";

import { SeverityBadge } from "@/components/badges/SeverityBadge";
import { RelativeTime } from "@/components/badges/RelativeTime";
import { Button, EmptyState } from "@/components/ui/primitives";
import type { EventFilters } from "@/lib/filters";
import type { EventLike } from "@/lib/events";

const COLUMNS = [
  "timestamp", "severity", "event_type", "source", "description",
  "username", "source_ip", "process_name", "score", "incident",
] as const;

export function EventTable({
  events,
  onSelect,
  selectedId,
  filters,
  onFiltersChange,
  nextCursor,
  onPage,
  onPrevious,
}: {
  events: EventLike[];
  onSelect: (event: EventLike) => void;
  selectedId: number | null;
  filters: EventFilters;
  onFiltersChange: (filters: EventFilters) => void;
  nextCursor?: string | null;
  onPage?: (cursor: string) => void;
  onPrevious?: () => void;
}) {
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [visible, setVisible] = useState<ReadonlyArray<string>>(COLUMNS);
  const features = useMemo(
    () =>
      tableFeatures({
        columnFilteringFeature,
        globalFilteringFeature,
        filteredRowModel: createFilteredRowModel(),
        filterFns,
      }),
    [],
  );
  const columns = useMemo(
    () =>
      COLUMNS.map((id) => ({
        accessorKey: id,
        header: id,
        cell: ({ row }: { row: { original: EventLike } }) => {
          const event = row.original;
          if (id === "severity") return <SeverityBadge severity={event.severity} />;
          if (id === "timestamp") return <RelativeTime value={event.timestamp} />;
          if (id === "incident") return "—";
          const value = event[id];
          return value === undefined || value === null ? "—" : String(value);
        },
      })),
    [],
  );
  const table = useTable({
    features,
    data: events,
    columns,
    state: { globalFilter: filters.search },
    onGlobalFilterChange: (search: string) => onFiltersChange({ ...filters, search }),
    globalFilterFn: "includesString",
  });
  const rows = table.getRowModel().rows;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA") return;
      if (event.key === "/") {
        event.preventDefault();
        document.getElementById("event-search")?.focus();
      } else if (event.key === "j") {
        setSelectedIndex((index) => Math.min(index + 1, rows.length - 1));
      } else if (event.key === "k") {
        setSelectedIndex((index) => Math.max(index - 1, 0));
      } else if (event.key === "Enter" && selectedIndex >= 0) {
        onSelect(rows[selectedIndex]!.original);
      } else if (event.key === "Escape") {
        setSelectedIndex(-1);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onSelect, rows, selectedIndex]);

  return (
    <div className="space-y-2">
      <fieldset className="flex flex-wrap gap-2 text-xs" aria-label="Visible columns">
        <legend className="sr-only">Visible columns</legend>
        {COLUMNS.map((column) => (
          <label key={column} className="inline-flex items-center gap-1">
            <input
              type="checkbox"
              checked={visible.includes(column)}
              onChange={() =>
                setVisible((current) =>
                  current.includes(column)
                    ? current.filter((item) => item !== column)
                    : [...current, column],
                )
              }
            />
            {column}
          </label>
        ))}
      </fieldset>
      {rows.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="max-h-[70vh] overflow-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="sticky top-0 z-10 bg-white dark:bg-slate-900">
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers
                    .filter((header) => visible.includes(header.column.id))
                    .map((header) => (
                      <th key={header.id} scope="col" className="border-b border-slate-200 px-2 py-1">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                    ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr
                  key={row.id}
                  className={`cursor-pointer border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800 ${
                    selectedIndex === index || selectedId === row.original.id ? "bg-blue-50 dark:bg-blue-950" : ""
                  }`}
                  onClick={() => onSelect(row.original)}
                >
                  {row
                    .getAllCells()
                    .filter((cell) => visible.includes(cell.column.id))
                    .map((cell) => (
                      <td key={cell.id} className="px-2 py-1">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {onPage || onPrevious ? (
        <nav aria-label="Event pagination" className="flex gap-2 text-sm">
          <Button disabled={!onPrevious} onClick={() => onPrevious?.()}>Previous</Button>
          <Button disabled={!nextCursor} onClick={() => nextCursor && onPage?.(nextCursor)}>
            Next
          </Button>
        </nav>
      ) : null}
    </div>
  );
}

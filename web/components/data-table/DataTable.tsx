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

import { Button, EmptyState } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

export interface DataTableProps<T extends Record<string, unknown>> {
  rows: T[];
  columns: ReadonlyArray<keyof T & string>;
  cursor?: string | null;
  nextCursor?: string | null;
  onPage?: (cursor: string) => void;
  onPrevious?: () => void;
  filterKey?: string;
  title?: string;
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function DataTable<T extends Record<string, unknown>>({
  rows,
  columns,
  cursor,
  nextCursor,
  onPage,
  onPrevious,
  filterKey = "q",
  title = "items",
}: DataTableProps<T>) {
  const [query, setQuery] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get(filterKey) ?? "";
  });
  const [visible, setVisible] = useState<ReadonlyArray<string>>(columns);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (query) params.set(filterKey, query);
    else params.delete(filterKey);
    const search = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
  }, [query, filterKey]);

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
  const tableColumns = useMemo(
    () =>
      columns.map((id) => ({
        accessorKey: id,
        header: id,
        cell: ({ getValue }: { getValue: () => unknown }) => cellText(getValue()),
      })),
    [columns],
  );
  const table = useTable({
    features,
    data: rows,
    columns: tableColumns,
    state: { globalFilter: query },
    onGlobalFilterChange: setQuery,
    globalFilterFn: "includesString",
  });
  const shown = table.getRowModel().rows;

  const exportCsv = () => {
    const header = visible.join(",");
    const lines = shown.map((row) =>
      visible
        .map((column) => `"${cellText(row.getValue(column)).replaceAll('"', '""')}"`)
        .join(","),
    );
    const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${title}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const toggleColumn = (column: string) => {
    setVisible((current) =>
      current.includes(column) ? current.filter((item) => item !== column) : [...current, column],
    );
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm" htmlFor="table-filter">
          Filter
          <input
            id="table-filter"
            className="ml-2 rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-800"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Filter ${title}`}
          />
        </label>
        <fieldset className="flex flex-wrap items-center gap-2 text-xs">
          <legend className="sr-only">Visible columns</legend>
          {columns.map((column) => (
            <label key={column} className="inline-flex items-center gap-1">
              <input
                type="checkbox"
                checked={visible.includes(column)}
                onChange={() => toggleColumn(column)}
              />
              {column}
            </label>
          ))}
        </fieldset>
        <Button onClick={exportCsv} aria-label={`Export ${title} as CSV`}>
          Export CSV
        </Button>
      </div>

      {shown.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id} className="border-b border-slate-200 dark:border-slate-700">
                  {group.headers
                    .filter((header) => visible.includes(header.column.id))
                    .map((header) => (
                      <th key={header.id} scope="col" className="px-3 py-2 font-semibold">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                    ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-slate-100 dark:border-slate-800"
                >
                  {row
                    .getAllCells()
                    .filter((cell) => visible.includes(cell.column.id))
                    .map((cell) => (
                      <td
                        key={cell.id}
                        className={cn(
                          "px-3 py-2",
                          cell.column.id === "severity" && "font-medium",
                        )}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {onPage || nextCursor ? (
        <nav aria-label="Table pagination" className="flex items-center gap-2 text-sm">
          <Button disabled={!cursor || !onPrevious} onClick={() => onPrevious?.()}>
            Previous
          </Button>
          <Button disabled={!nextCursor} onClick={() => nextCursor && onPage?.(nextCursor)}>
            Next
          </Button>
        </nav>
      ) : null}
    </div>
  );
}

"use client";

import { Button } from "@/components/ui/primitives";

export interface SavedFilter {
  id: number;
  name: string;
  page: string;
  query: Record<string, unknown>;
}

export function SavedFilters({
  saved,
  onApply,
  onSave,
  onDelete,
}: {
  saved: SavedFilter[];
  onApply: (query: Record<string, unknown>) => void;
  onSave: () => void;
  onDelete: (identifier: number) => void;
}) {
  return (
    <section aria-label="Saved filters" className="flex flex-wrap items-center gap-2 text-sm">
      <Button onClick={onSave}>Save current filter</Button>
      {saved
        .filter((item) => item.page === "events")
        .map((item) => (
          <span key={item.id} className="inline-flex items-center gap-1 rounded border border-slate-300 px-2 py-1 dark:border-slate-600">
            <button
              type="button"
              className="text-blue-700 underline dark:text-blue-300"
              onClick={() => onApply(item.query)}
              aria-label={`Apply ${item.name}`}
            >
              {item.name}
            </button>
            <button
              type="button"
              className="text-xs text-slate-500"
              onClick={() => onDelete(item.id)}
              aria-label={`Delete ${item.name}`}
            >
              ✕
            </button>
          </span>
        ))}
    </section>
  );
}

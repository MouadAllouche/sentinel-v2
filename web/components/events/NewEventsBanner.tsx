"use client";

export function NewEventsBanner({ count, onLoad }: { count: number; onLoad: () => void }) {
  if (count <= 0) return null;
  return (
    <div role="status" aria-live="polite" className="rounded border border-blue-300 bg-blue-50 p-2 text-center text-sm dark:border-blue-700 dark:bg-blue-950">
      <button type="button" className="text-blue-800 underline dark:text-blue-200" onClick={onLoad}>
        {count} new {count === 1 ? "event" : "events"} — click to load
      </button>
    </div>
  );
}

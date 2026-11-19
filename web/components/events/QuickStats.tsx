"use client";

import { groupBySeverity, type EventLike } from "@/lib/events";

const SEVERITIES = ["low", "medium", "high", "critical"];

export function QuickStats({
  events,
  total,
  onBrush,
}: {
  events: EventLike[];
  total?: number;
  onBrush?: (since: string, until: string) => void;
}) {
  const counts = groupBySeverity(events);
  const buckets = new Map<string, number>();
  for (const event of events) {
    const key = event.timestamp.slice(0, 13);
    buckets.set(key, (buckets.get(key) ?? 0) + 1);
  }
  const times = [...buckets.keys()].sort();
  return (
    <section aria-label="Quick stats" className="rounded border border-slate-200 p-3 text-sm dark:border-slate-700">
      <p>
        <strong>{total ?? events.length}</strong> matching events
      </p>
      <div className="mt-2 flex flex-wrap gap-3">
        {SEVERITIES.map((severity) => (
          <span key={severity} className="flex items-center gap-1">
            {severity}
            <span className="inline-block h-2 w-8 bg-slate-200 dark:bg-slate-700">
              <span
                className="block h-2 bg-blue-600"
                style={{ width: `${events.length ? ((counts[severity] ?? 0) / events.length) * 100 : 0}%` }}
              />
            </span>
            {counts[severity] ?? 0}
          </span>
        ))}
      </div>
      {times.length > 1 ? (
        <div className="mt-2 flex items-end gap-1" aria-label="Time histogram">
          {times.map((time) => (
            <button
              key={time}
              type="button"
              className="w-4 bg-slate-300 dark:bg-slate-600"
              style={{ height: `${Math.max(4, (buckets.get(time) ?? 0) * 8)}px` }}
              aria-label={`Select bucket ${time}`}
              onClick={() => onBrush?.(`${time}:00:00+00:00`, `${time}:59:59+00:00`)}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

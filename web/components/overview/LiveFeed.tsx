"use client";

import { useEffect, useRef, useState } from "react";

import { RelativeTime } from "@/components/badges/RelativeTime";
import { SeverityBadge } from "@/components/badges/SeverityBadge";
import { Button, Card } from "@/components/ui/primitives";
import type { EventLike } from "@/lib/events";
import type { StreamStatus } from "@/lib/sse";

const STATUS_TEXT: Record<StreamStatus, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
  polling: "Polling",
  paused: "Paused",
};

export function LiveFeed({
  events,
  status,
  paused,
  onTogglePause,
  now,
}: {
  events: EventLike[];
  status: StreamStatus;
  paused: boolean;
  onTogglePause: () => void;
  now: string;
}) {
  const previousIds = useRef<Set<number>>(new Set(events.map((event) => event.id)));
  const [highlighted, setHighlighted] = useState<Set<number>>(new Set());

  useEffect(() => {
    const fresh = events.filter((event) => !previousIds.current.has(event.id)).map((event) => event.id);
    for (const event of events) previousIds.current.add(event.id);
    if (fresh.length === 0) return;
    setHighlighted(new Set(fresh));
    const timer = setTimeout(() => setHighlighted(new Set()), 3000);
    return () => clearTimeout(timer);
  }, [events]);

  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Live feed</h2>
        <div className="flex items-center gap-2">
          <span role="status" aria-live="polite" className="text-xs text-slate-600 dark:text-slate-300">
            {paused ? "Paused" : STATUS_TEXT[status]}
          </span>
          <Button
            aria-label={paused ? "Resume live feed" : "Pause live feed"}
            onClick={onTogglePause}
          >
            {paused ? "Resume" : "Pause"}
          </Button>
        </div>
      </div>
      {events.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">No events yet.</p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800" aria-label="Latest events">
          {events.map((event) => (
            <li
              key={event.id}
              className={`flex items-center gap-2 py-2 text-sm ${
                highlighted.has(event.id)
                  ? "animate-pulse bg-blue-50 dark:bg-blue-950 motion-reduce:animate-none"
                  : ""
              }`}
            >
              <SeverityBadge severity={event.severity} />
              <span className="font-medium">{event.event_type}</span>
              <span className="truncate text-slate-600 dark:text-slate-300">{event.description}</span>
              <span className="ml-auto shrink-0 text-xs text-slate-500">
                <RelativeTime value={event.timestamp} now={now} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

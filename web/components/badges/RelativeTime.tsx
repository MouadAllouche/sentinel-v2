"use client";

import { formatInTimeZone } from "date-fns-tz";
import { useSyncExternalStore } from "react";

import { formatRelative } from "@/lib/format";

const noopSubscribe = () => () => {};

/**
 * Server render and hydration show the same absolute UTC text; only after the
 * client takes over do we switch to relative text and the viewer's timezone.
 * `useSyncExternalStore` is the mount signal (no effect, no setState-in-effect,
 * and stable snapshots), so the clock and localStorage are never read while
 * producing hydration-sensitive markup.
 */
export function RelativeTime({ value, now }: { value: string; now?: string }) {
  const hydrated = useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );

  const parsed = new Date(value);
  let absolute = formatInTimeZone(parsed, "UTC", "yyyy-MM-dd HH:mm:ss") + " UTC";
  if (Number.isNaN(parsed.getTime())) absolute = "unknown time";

  if (!hydrated) {
    return (
      <time dateTime={value} title={absolute}>
        {absolute}
      </time>
    );
  }

  const timezone =
    typeof window === "undefined"
      ? "UTC"
      : window.localStorage.getItem("sentinel-timezone") || "UTC";
  const reference = now ?? new Date().toISOString();
  return (
    <time dateTime={value} title={`${absolute} (${timezone})`}>
      {formatRelative(value, reference)} ago
    </time>
  );
}

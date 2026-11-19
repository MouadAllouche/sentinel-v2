"use client";

import { formatInTimeZone } from "date-fns-tz";
import { useState } from "react";

import { formatRelative } from "@/lib/format";

export function RelativeTime({ value, now }: { value: string; now?: string }) {
  const [reference] = useState(() => now ?? new Date().toISOString());
  const [timezone] = useState(() => {
    if (typeof window === "undefined") return "UTC";
    return window.localStorage.getItem("sentinel-timezone") || "UTC";
  });
  let absolute = formatInTimeZone(new Date(value), timezone, "yyyy-MM-dd HH:mm:ss");
  if (Number.isNaN(new Date(value).getTime())) absolute = "unknown time";
  return (
    <time dateTime={value} title={`${absolute} (${timezone})`}>
      {formatRelative(value, reference)} ago
    </time>
  );
}

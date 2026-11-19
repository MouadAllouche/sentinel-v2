"use client";

import { useState } from "react";

import { CriticalIncidents } from "@/components/overview/CriticalIncidents";
import { EventsOverTime } from "@/components/overview/EventsOverTime";
import { FirstRunChecklist } from "@/components/overview/FirstRunChecklist";
import { HealthStrip } from "@/components/overview/HealthStrip";
import { KpiCard } from "@/components/overview/KpiCard";
import { LiveFeed } from "@/components/overview/LiveFeed";
import { RuleActivity } from "@/components/overview/RuleActivity";
import { TopList } from "@/components/overview/TopList";
import {
  useApiList,
  useEventStats,
  useEvents,
  useHealth,
  useIncidents,
  useTopValues,
} from "@/lib/api/hooks";
import type { EventLike } from "@/lib/events";
import { formatDelta, rangeForPreset } from "@/lib/filters";
import { useLiveUpdates } from "@/lib/sse";

function sumBuckets(buckets: Array<{ total: number }>): number {
  return buckets.reduce((total, bucket) => total + bucket.total, 0);
}

export function Overview() {
  const [now] = useState(() => new Date().toISOString());
  const [paused, setPaused] = useState(false);
  const current = rangeForPreset("24h", now);
  const previousRange = rangeForPreset("48h", now);
  const previous = {
    since: previousRange.since,
    until: current.since,
  };
  const currentStats = useEventStats({ bucket: "hour", group_by: "severity", ...current });
  const previousStats = useEventStats({ bucket: "hour", group_by: "severity", ...previous });
  const failed = useEvents({
    event_type: ["failed_login"],
    since: current.since,
    until: current.until,
    limit: 500,
  });
  const allowlisted = useEvents({
    allowlisted: true,
    since: current.since,
    until: current.until,
    limit: 500,
  });
  const network = useEvents({
    event_type: ["network_connection"],
    since: current.since,
    until: current.until,
    limit: 500,
  });
  const incidents = useIncidents();
  const findings = useApiList<Record<string, unknown>>("/api/rules/findings");
  const health = useHealth();
  const collectors = useApiList<Record<string, unknown>>("/api/collectors");
  const baselines = useApiList<Record<string, unknown>>("/api/baselines");
  const channels = useApiList<Record<string, unknown>>("/api/notifications/channels");
  const feed = useEvents({ limit: 20 });
  const live = useLiveUpdates({ paused });

  const total = sumBuckets(currentStats.data ?? []);
  const previousTotal = sumBuckets(previousStats.data ?? []);
  const openIncidents = (incidents.data ?? []).filter((item) => item.status !== "closed");
  const criticalHigh = openIncidents.filter((item) =>
    ["critical", "high"].includes(item.severity),
  ).length;
  const firstRun =
    total === 0 && previousTotal === 0 && !currentStats.isLoading && !previousStats.isLoading;

  const withRange = (extra: Record<string, string> = {}) =>
    `?${new URLSearchParams({ since: current.since, until: current.until, ...extra }).toString()}`;
  const kpis = [
    {
      label: "Events (24 h)",
      value: total,
      delta: formatDelta(total, previousTotal),
      href: `/events${withRange()}`,
    },
    {
      label: "Failed logins (24 h)",
      value: failed.data?.total ?? 0,
      href: `/events${withRange({ event_type: "failed_login" })}`,
    },
    {
      label: "Open incidents",
      value: openIncidents.length,
      href: "/incidents",
    },
    {
      label: "Critical/high incidents",
      value: criticalHigh,
      href: "/incidents?severity=critical&severity=high",
    },
    {
      label: "Active rule findings (24 h)",
      value: (findings.data?.items ?? []).filter((item) => {
        const stamp = String(item.created_at ?? item.timestamp ?? "");
        return !stamp || stamp >= current.since;
      }).length,
      href: "/rules",
    },
    {
      label: "Suppressed events (24 h)",
      value: allowlisted.data?.total ?? 0,
      href: `/events${withRange({ allowlisted: "true" })}`,
    },
    {
      label: "Connections seen (24 h)",
      value: network.data?.total ?? 0,
      href: `/events${withRange({ event_type: "network_connection" })}`,
    },
  ];

  const mature = (baselines.data?.items ?? []).filter(
    (item) => String(item.status ?? "").toLowerCase() === "mature",
  ).length;
  const notificationEnabled = (channels.data?.items ?? []).some((item) => item.enabled === true);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Overview</h1>
      {firstRun ? (
        <FirstRunChecklist />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {kpis.map((kpi) => (
              <KpiCard
                key={kpi.label}
                label={kpi.label}
                value={kpi.value}
                delta={kpi.delta}
                href={kpi.href}
                loading={currentStats.isLoading}
                error={currentStats.isError ? "Could not load KPIs" : null}
                onRetry={() => void currentStats.refetch()}
              />
            ))}
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <EventsOverTime />
            </div>
            <TopListField field="event_type" title="Event types" range={current} />
          </div>
        </>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <TopListField field="source_ip" title="Top source IPs" range={current} />
        <TopListField field="username" title="Top usernames" range={current} />
        <TopListField field="process_name" title="Top processes" range={current} />
        <RuleActivity />
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <CriticalIncidents />
        <LiveFeed
          events={(feed.data?.items ?? []) as EventLike[]}
          status={live.status}
          paused={paused}
          onTogglePause={() => setPaused((value) => !value)}
          now={now}
        />
      </div>
      <HealthStrip
        health={health.data}
        collectors={collectors.data?.items as Array<{ name: string; status: string; warnings?: string[] }> ?? []}
        baselines={{ mature, total: (baselines.data?.items ?? []).length }}
        notificationsEnabled={notificationEnabled}
        now={now}
      />
    </div>
  );
}

function TopListField({
  field,
  title,
  range,
}: {
  field: string;
  title: string;
  range?: { since: string; until: string };
}) {
  const query = useTopValues(field);
  return <TopList title={title} field={field} items={query.data ?? []} range={range} />;
}

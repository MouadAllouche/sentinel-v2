"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/primitives";
import { RetentionPanel } from "@/components/settings/RetentionPanel";
import { Button, Card, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { client } from "@/lib/api/client";
import { useApiList, useRetentionPolicy, useSystemInfo } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";

type Tab = "retention" | "display" | "engine" | "about";

export function SettingsRoute() {
  const [tab, setTab] = useState<Tab>("retention");
  const [dryRun, setDryRun] = useState<{ pruned?: number } | null>(null);
  const [applying, setApplying] = useState(false);
  const [timezone, setTimezone] = useState(() =>
    typeof window === "undefined" ? "UTC" : window.localStorage.getItem("sentinel-timezone") ?? "UTC",
  );
  const [density, setDensity] = useState(() =>
    typeof window === "undefined"
      ? "comfortable"
      : window.localStorage.getItem("sentinel-density") ?? "comfortable",
  );
  const [range, setRange] = useState(() =>
    typeof window === "undefined" ? "24h" : window.localStorage.getItem("sentinel-range") ?? "24h",
  );
  const [edits, setEdits] = useState<Record<string, number> | null>(null);
  const me = useMe();
  const { show } = useToast();
  const policy = useRetentionPolicy();
  const cycles = useApiList<Record<string, unknown>>("/api/cycles");
  const info = useSystemInfo();

  if (policy.isLoading) return <Skeleton rows={4} />;
  if (policy.isError) return <ErrorState message="Could not load settings." />;
  const events = (edits ??
    (policy.data?.events as Record<string, number> | undefined) ?? {}) as Record<string, number>;
  const db = info.data?.db ?? {};

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Settings</h1>
      <div className="flex flex-wrap gap-2">
        {(["retention", "display", "engine", "about"] as const).map((item) => (
          <button
            key={item}
            type="button"
            aria-current={tab === item ? "page" : undefined}
            onClick={() => setTab(item)}
            className={`rounded px-3 py-1 text-sm ${tab === item ? "bg-slate-900 text-white" : "border border-slate-300 dark:border-slate-600"}`}
          >
            {item}
          </button>
        ))}
      </div>
      {tab === "retention" ? (
        <RetentionPanel
          policy={{ events }}
          onChange={(next) => setEdits(next.events)}
          onSave={() => {
            void client
              .PUT("/api/settings/retention", {
                body: { ...(policy.data ?? {}), events },
              })
              .then(() => {
                show("Retention policy saved", "success");
                void policy.refetch();
              })
              .catch(() => show("Could not save the policy"));
          }}
          dryRun={dryRun}
          onPreview={() => {
            void client
              .POST("/api/retention/dry-run")
              .then(({ data }) => setDryRun(data as { pruned?: number } | undefined ?? null))
              .catch(() => show("Dry run failed"));
          }}
          onApply={() => setApplying(true)}
          role={me.role}
        />
      ) : null}
      {tab === "display" ? (
        <Card>
          <h2 className="font-semibold">Display</h2>
          <label className="mt-2 block text-sm">Timezone
            <select
              aria-label="Display timezone"
              className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
              value={timezone}
              onChange={(event) => {
                setTimezone(event.target.value);
                window.localStorage.setItem("sentinel-timezone", event.target.value);
              }}
            >
              <option value="UTC">UTC</option><option value="local">Local</option>
            </select>
          </label>
          <label className="mt-2 block text-sm">Density
            <select
              aria-label="Density"
              className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
              value={density}
              onChange={(event) => {
                setDensity(event.target.value);
                window.localStorage.setItem("sentinel-density", event.target.value);
              }}
            >
              <option value="comfortable">comfortable</option><option value="compact">compact</option>
            </select>
          </label>
          <label className="mt-2 block text-sm">Default range
            <select
              aria-label="Default range"
              className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
              value={range}
              onChange={(event) => {
                setRange(event.target.value);
                window.localStorage.setItem("sentinel-range", event.target.value);
              }}
            >
              <option value="24h">24 h</option><option value="7d">7 d</option><option value="30d">30 d</option>
            </select>
          </label>
          <p className="mt-2 text-xs text-slate-500">Stored locally in your browser; never on the server.</p>
        </Card>
      ) : null}
      {tab === "engine" ? (
        <Card>
          <h2 className="font-semibold">Engine</h2>
          <p className="mt-1 text-sm">Last cycle: {String(cycles.data?.items[0]?.status ?? "none")}</p>
          <Button
            className="mt-2"
            disabled={me.role !== "admin"}
            onClick={() => {
              void client.POST("/api/engine/run").then(() => {
                show("Cycle started", "success");
                void cycles.refetch();
              }).catch(() => show("Could not run the cycle"));
            }}
          >
            Run cycle now
          </Button>
        </Card>
      ) : null}
      {tab === "about" ? (
        <Card>
          <h2 className="font-semibold">About</h2>
          <p className="mt-1 text-sm">Version: {info.data?.version ?? "sentinel-2"}</p>
          <p className="text-sm">Schema version: {info.data?.schema_version ?? "—"}</p>
          <p className="text-sm">
            DB size: {String(db.size_bytes ?? 0)} bytes · events: {String(db.event_count ?? 0)} ·
            oldest event: {String(db.oldest_event ?? "—")}
          </p>
        </Card>
      ) : null}
      {applying ? (
        <ConfirmDialog
          title="Apply retention policy?"
          confirmPhrase="APPLY"
          onCancel={() => setApplying(false)}
          onConfirm={() => {
            setApplying(false);
            void client.POST("/api/retention/apply").then(() => {
              show("Retention applied", "success");
              void policy.refetch();
            }).catch(() => show("Could not apply retention"));
          }}
        />
      ) : null}
    </div>
  );
}

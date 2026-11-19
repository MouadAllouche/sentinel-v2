"use client";

import { useState } from "react";

import { OverrideList } from "@/components/severity/OverrideList";
import { ReapplyPanel } from "@/components/severity/ReapplyPanel";
import { SeverityDefaults, type SeverityRow } from "@/components/severity/SeverityDefaults";
import { Button, Card, ConfirmDialog, ErrorState, Input, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { ApiError, client } from "@/lib/api/client";
import { useApiList, useTopValues } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";
import { validateThresholds } from "@/lib/rules/helpers";

export function SeverityRoute() {
  const [tab, setTab] = useState<"defaults" | "overrides" | "apply">("defaults");
  const [dirty, setDirty] = useState(false);
  const [resetAll, setResetAll] = useState(false);
  const [edits, setEdits] = useState<Record<string, Partial<SeverityRow>>>({});
  const [testResult, setTestResult] = useState<{ severity: string; severity_source: string } | null>(null);
  const [preview, setPreview] = useState<{ changed: number; by_severity?: Record<string, number> } | null>(null);
  const [bands, setBands] = useState({ medium: 20, high: 40, critical: 70 });
  const me = useMe();
  const { show } = useToast();
  const defaults = useApiList<Record<string, unknown>>("/api/severity/defaults");
  const overrides = useApiList<Record<string, unknown>>("/api/severity/overrides");
  const top = useTopValues("event_type", 50);
  const rows: SeverityRow[] = (defaults.data?.items ?? []).map((item) => ({
    event_type: String(item.event_type ?? item.key ?? ""),
    severity: String(item.severity ?? "low"),
    points: Number(item.points ?? 0),
    events_24h: top.data?.find((value) => value.value === String(item.event_type ?? item.key))?.total ?? 0,
    modified: Boolean(item.modified),
    enabled: item.enabled !== false,
    ...(edits[String(item.event_type ?? item.key)] ?? {}),
  }));
  const overrideRows = (overrides.data?.items ?? []).map((item) => ({
    id: Number(item.id),
    name: String(item.name ?? item.scope ?? item.id),
    enabled: Boolean(item.enabled),
    builtin: Boolean(item.builtin),
    modified: Boolean(item.modified),
    severity: String(item.severity ?? "low"),
    conditions: item.conditions,
  }));
  const thresholdError = validateThresholds(bands);

  return (
    <Card>
      <div className="mb-3 flex gap-2">
        {(["defaults", "overrides", "apply"] as const).map((item) => (
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
      {defaults.isLoading ? <Skeleton rows={5} /> : defaults.isError ? (
        <ErrorState message="Could not load severity settings." onRetry={() => void defaults.refetch()} />
      ) : (
        <>
          {tab === "defaults" ? (
            <SeverityDefaults
              rows={rows}
              dirty={dirty}
              onSave={() => {
                void Promise.all(
                  rows.map((row) =>
                    client.PUT("/api/severity/defaults/{event_type}", {
                      params: { path: { event_type: row.event_type } },
                      body: {
                        severity: row.severity,
                        points: row.points,
                        enabled: row.enabled !== false,
                      },
                    }),
                  ),
                ).then(() => {
                  setDirty(false);
                  show("Defaults saved", "success");
                  void defaults.refetch();
                }).catch(() => show("Could not save defaults"));
              }}
              onChange={(index, changes) => {
                const key = rows[index]?.event_type;
                if (!key) return;
                setEdits((current) => ({ ...current, [key]: { ...current[key], ...changes } }));
                setDirty(true);
              }}
              onResetRow={(eventType) => {
                void client
                  .POST("/api/severity/defaults/{event_type}/reset", {
                    params: { path: { event_type: eventType } },
                  })
                  .then(() => {
                    setEdits((current) => ({ ...current, [eventType]: {} }));
                    void defaults.refetch();
                    show("Default reset", "success");
                  })
                  .catch(() => show("Could not reset the default"));
              }}
              onResetAll={() => setResetAll(true)}
              currentRole={me.role}
            />
          ) : null}
          {tab === "overrides" ? (
            <OverrideList
              overrides={overrideRows}
              onReorder={(ids) => {
                const order = Object.fromEntries(ids.map((id, index) => [String(id), index]));
                void client.POST("/api/severity/overrides/reorder", { body: { order } })
                  .then(() => void overrides.refetch())
                  .catch(() => show("Could not reorder overrides"));
              }}
              currentRole={me.role}
              onUpdate={(override, changes) => {
                void client
                  .PUT("/api/severity/overrides/{identifier}", {
                    params: { path: { identifier: String(override.id) } },
                    body: changes as unknown as Record<string, unknown>,
                  })
                  .then(() => void overrides.refetch())
                  .catch(() => show("Could not update the override"));
              }}
              onDelete={(identifier) => {
                void client
                  .DELETE("/api/severity/overrides/{identifier}", {
                    params: { path: { identifier: String(identifier) } },
                  })
                  .then(() => void overrides.refetch())
                  .catch(() => show("Could not delete the override"));
              }}
              onReset={(identifier) => {
                void client
                  .POST("/api/severity/overrides/{identifier}/reset", {
                    params: { path: { identifier: String(identifier) } },
                  })
                  .then(() => void overrides.refetch())
                  .catch(() => show("Could not reset the override"));
              }}
              onCreate={() => {
                const name = window.prompt("Override name");
                if (!name) return;
                void client
                  .POST("/api/severity/overrides", {
                    body: {
                      name,
                      priority: overrideRows.length + 1,
                      conditions: { all: [{ field: "event_type", op: "eq", value: "failed_login" }] },
                      severity: "medium",
                    },
                  })
                  .then(() => void overrides.refetch())
                  .catch(() => show("Could not create the override"));
              }}
              onDuplicate={(identifier) => {
                const source = overrideRows.find((row) => row.id === identifier);
                if (!source) return;
                void client
                  .POST("/api/severity/overrides", {
                    body: {
                      name: `${source.name} copy`,
                      priority: overrideRows.length + 1,
                      conditions: source.conditions ?? { all: [] },
                      severity: source.severity ?? "medium",
                    },
                  })
                  .then(() => void overrides.refetch())
                  .catch(() => show("Could not duplicate the override"));
              }}
              onTest={(sample) => {
                let event: Record<string, unknown>;
                try {
                  event = JSON.parse(sample) as Record<string, unknown>;
                } catch {
                  show("Paste a valid JSON event");
                  return;
                }
                void client
                  .POST("/api/severity/overrides/test", { body: { event } })
                  .then(({ data }) => {
                    setTestResult(
                      (data as { severity: string; severity_source: string } | undefined) ?? null,
                    );
                  })
                  .catch(() => show("Could not test this event"));
              }}
            />
          ) : null}
          {testResult ? (
            <p role="status" className="text-sm">
              Result: {testResult.severity} from {testResult.severity_source}
            </p>
          ) : null}
          {tab === "apply" ? (
            <div className="space-y-4">
              <ReapplyPanel
                preview={preview}
                onPreview={() => {
                  void client.POST("/api/events/reapply-severity", { body: { filters: {}, dry_run: true } })
                    .then(({ data }) => {
                      const value = data as { changed?: number } | undefined;
                      setPreview({ changed: value?.changed ?? 0 });
                    })
                    .catch((cause) => show(cause instanceof ApiError ? cause.message : "Preview failed"));
                }}
                onApply={() => {
                  void client.POST("/api/events/reapply-severity", { body: { filters: {}, dry_run: false } })
                    .then(() => show("Severity re-applied", "success"))
                    .catch(() => show("Could not re-apply severity"));
                }}
                currentRole={me.role}
              />
              <section aria-label="Risk thresholds" className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
                <h2 className="font-semibold">Risk thresholds</h2>
                {(["medium", "high", "critical"] as const).map((key) => (
                  <label key={key} className="mr-3 text-sm">
                    {key}
                    <Input
                      aria-label={`Threshold ${key}`}
                      type="number"
                      className="ml-1 w-20"
                      value={bands[key]}
                      onChange={(event) => setBands({ ...bands, [key]: Number(event.target.value) })}
                    />
                  </label>
                ))}
                {thresholdError ? <p role="alert" className="text-sm text-red-700">{thresholdError}</p> : null}
                <Button disabled={Boolean(thresholdError) || me.role !== "admin"} onClick={() => {
                  void client.PUT("/api/risk/thresholds", { body: bands }).then(() => show("Thresholds saved", "success"));
                }}>Save thresholds</Button>
              </section>
            </div>
          ) : null}
        </>
      )}
      {resetAll ? (
        <ConfirmDialog
          title="Reset all severity defaults?"
          confirmPhrase="RESET"
          onCancel={() => setResetAll(false)}
          onConfirm={() => {
            setResetAll(false);
            void client
              .POST("/api/severity/defaults/reset")
              .then(() => {
                setEdits({});
                setDirty(false);
                void defaults.refetch();
                show("All defaults reset", "success");
              })
              .catch(() => show("Could not reset defaults"));
          }}
        />
      ) : null}
    </Card>
  );
}

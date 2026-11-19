"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import { ConditionBuilder } from "@/components/conditions/ConditionBuilder";
import { PreviewPanel, type PreviewResult } from "@/components/rules/PreviewPanel";
import { SaveDiffDialog } from "@/components/rules/SaveDiffDialog";
import { TierEditor } from "@/components/rules/TierEditor";
import { VersionHistory } from "@/components/rules/VersionHistory";
import { Button, Input, Label } from "@/components/ui/primitives";
import { ConfirmDialog } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { ApiError, client } from "@/lib/api/client";
import { useMe } from "@/lib/auth";
import { definitionForKind, diffRules, mapServerErrors, type DiffEntry, type TierLike } from "@/lib/rules/helpers";
import { ruleSchema } from "@/lib/rules/schema";

const blank = {
  id: "",
  name: "",
  description: "",
  kind: "threshold",
  enabled: true,
  match: { event_types: ["failed_login"], conditions: { all: [] as unknown[] } },
  scope: { exclude_allowlisted: true },
  actions: { create_incident: true, notify: true, tags: [] as string[] },
  mitre: [] as string[],
  group_by: ["source_ip"] as string[],
  aggregate: { type: "count", field: null as string | null },
  window_mode: "sliding",
  fixed_alignment: null as string | null,
  cooldown_seconds: 0,
  tiers: [{ label: "Medium", count: 5, window_seconds: 600, severity: "medium", points: 5 }] as TierLike[],
  z_tiers: [] as Array<{ label: string; z: number; min_absolute: number; severity: string; points: number }>,
  steps: [] as Array<Record<string, unknown>>,
  correlate_on: [] as string[],
  within_seconds: 0,
  field: null as string | null,
  per: null as string | null,
  learning_days: 30,
  min_history_events: 0,
  metric: null as string | null,
  subject: null as string | null,
  min_std: 1,
  meta_conditions: [] as Array<{ metric: string; op: string; value: number }>,
};

type Definition = typeof blank;

interface Catalogue {
  event_types: string[];
  group_by: string[];
  kinds: string[];
  mitre: Array<{ id: string; name: string; label: string }>;
  limits: { max_tiers: number };
}

function FieldError({ message }: { message?: string }) {
  return message ? (
    <p role="alert" className="text-sm text-red-700">{message}</p>
  ) : null;
}

export function RuleBuilder({ id }: { id?: string }) {
  const router = useRouter();
  const me = useMe();
  const { show } = useToast();
  const admin = me.role === "admin";
  const {
    control,
    setValue,
    reset,
    trigger,
    formState: { errors, isDirty },
  } = useForm<Definition>({
    resolver: zodResolver(ruleSchema) as never,
    defaultValues: blank,
    mode: "onChange",
  });
  const definition = useWatch({ control }) as Definition;
  const [json, setJson] = useState(JSON.stringify(blank, null, 2));
  const [mode, setMode] = useState<"form" | "json">("form");
  const [modeError, setModeError] = useState<string | null>(null);
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  const [catalogue, setCatalogue] = useState<Catalogue>({
    event_types: [], group_by: [], kinds: ["threshold"], mitre: [], limits: { max_tiers: 10 },
  });
  const [validation, setValidation] = useState<{ warnings: string[] }>({ warnings: [] });
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [range, setRange] = useState("7d");
  const [diffs, setDiffs] = useState<DiffEntry[] | null>(null);
  const [original, setOriginal] = useState<Definition | null>(null);
  const [versions, setVersions] = useState<Array<{ version: number; created_at: string; actor?: string }>>([]);
  const [restoreVersion, setRestoreVersion] = useState<number | null>(null);
  const [manualDirty, setManualDirty] = useState(false);

  useEffect(() => {
    void client.GET("/api/rules/schema").then(({ data }) => {
      if (data) setCatalogue(data as unknown as Catalogue);
    });
  }, []);

  useEffect(() => {
    if (!id) return;
    void client.GET("/api/rules/{identifier}", { params: { path: { identifier: id } } }).then(({ data }) => {
      if (!data) return;
      const loaded = data as unknown as Definition;
      reset(loaded);
      setOriginal(loaded);
      setJson(JSON.stringify(loaded, null, 2));
    });
    void client.GET("/api/rules/{identifier}/versions", { params: { path: { identifier: id } } }).then(({ data }) => {
      setVersions((data as Array<{ version: number; created_at: string; actor?: string }>) ?? []);
    });
  }, [id, reset]);

  useEffect(() => {
    if (!isDirty && !manualDirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isDirty, manualDirty]);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const { data } = await client.POST("/api/rules/validate", { body: { definition } });
        setValidation({ warnings: (data as { warnings?: string[] } | undefined)?.warnings ?? [] });
        setModeError(null);
      } catch (cause) {
        if (cause instanceof ApiError) {
          setModeError(cause.message);
          setServerErrors([]);
          mapServerErrors(cause.details ?? [], (_field, error) =>
            setServerErrors((current) => [...current, error.message]),
          );
        }
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [definition]);

  useEffect(() => {
    let cancelled = false;
    const until = new Date().toISOString();
    const since = new Date(Date.now() - ({ "24h": 1, "7d": 7, "30d": 30 }[range] ?? 7) * 86400000).toISOString();
    const timer = setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const { data } = await client.POST("/api/rules/preview", { body: { definition, since, until } });
        if (!cancelled) setPreview(data as unknown as PreviewResult);
      } catch {
        if (!cancelled) setPreview(null);
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [definition, range]);

  const updateZ = (index: number, changes: Record<string, unknown>) => {
    const next = (definition.tiers as unknown as Array<Record<string, unknown>>).map((item, position) =>
      position === index ? { ...item, ...changes } : item,
    );
    update({ tiers: next as unknown as TierLike[] });
  };
  const replaceDefinition = (next: Definition) => {
    reset(next);
    setManualDirty(true);
  };
  const update = (changes: Partial<Definition>) => {
    for (const [key, value] of Object.entries(changes)) {
      setValue(key as keyof Definition, value as never, { shouldDirty: true, shouldValidate: true });
    }
  };
  const switchMode = (next: "form" | "json") => {
    if (next === "form" && mode === "json") {
      try {
        reset(JSON.parse(json) as Definition);
        setModeError(null);
      } catch {
        setModeError("JSON is invalid — fix it before switching back to the form builder.");
        return;
      }
    } else if (next === "json") {
      setJson(JSON.stringify(definition, null, 2));
    }
    setMode(next);
  };

  const save = async () => {
    try {
      if (id) {
        await client.PUT("/api/rules/{identifier}", {
          params: { path: { identifier: id } },
          body: { definition },
        });
      } else {
        await client.POST("/api/rules", { body: { definition } });
      }
      show("Rule saved", "success");
      setDiffs(null);
      router.push("/rules");
    } catch (cause) {
      show(cause instanceof ApiError ? cause.message : "Could not save the rule");
    }
  };
  const confirmSave = () => {
    void trigger().then((valid) => {
      if (valid) setDiffs(diffRules(original ?? blank, definition));
    });
  };

  const highImpact = (preview?.total_findings ?? 0) > 100;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">{id ? "Edit rule" : "New rule"}</h1>
        {admin ? null : <span className="text-sm text-slate-500">View only</span>}
        <Button onClick={() => switchMode(mode === "form" ? "json" : "form")} disabled={!admin}>
          {mode === "form" ? "Edit JSON" : "Form builder"}
        </Button>
      </div>
      {modeError ? <p role="alert" className="text-sm text-red-700">{modeError}</p> : null}

      {mode === "json" ? (
        <textarea
          aria-label="Rule definition JSON"
          rows={24}
          className="w-full rounded border border-slate-300 p-2 font-mono text-sm dark:border-slate-600 dark:bg-slate-800"
          value={json}
          readOnly={!admin}
          onChange={(event) => {
            setJson(event.target.value);
            try {
              reset(JSON.parse(event.target.value) as Definition);
              setModeError(null);
            } catch {
              setModeError("JSON is invalid — fix it before switching back.");
            }
          }}
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <section className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
              <h2 className="font-semibold">Basics</h2>
              <Label htmlFor="rule-id">Rule id</Label>
              <Input id="rule-id" aria-label="Rule id" value={definition.id} readOnly={!admin || Boolean(id)} aria-describedby={errors.id ? "rule-id-error" : undefined} onChange={(event) => update({ id: event.target.value })} />
              <FieldError message={errors.id?.message} />
              <Label htmlFor="rule-name">Name</Label>
              <Input id="rule-name" aria-label="Rule name" value={definition.name} readOnly={!admin} aria-describedby={errors.name ? "rule-name-error" : undefined} onChange={(event) => update({ name: event.target.value })} />
              <FieldError message={errors.name?.message} />
              <Label htmlFor="rule-description">Description</Label>
              <Input id="rule-description" aria-label="Rule description" value={definition.description} readOnly={!admin} onChange={(event) => update({ description: event.target.value })} />
              <Label htmlFor="rule-tags">Tags (comma separated)</Label>
              <Input
                id="rule-tags"
                aria-label="Rule tags"
                value={definition.actions.tags.join(", ")}
                readOnly={!admin}
                onChange={(event) => update({ actions: { ...definition.actions, tags: event.target.value.split(",").map((tag) => tag.trim()).filter(Boolean) } })}
              />
              {!id ? (
                <label className="text-sm">
                  Kind
                  <select
                    aria-label="Rule kind"
                    className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                    value={definition.kind}
                    onChange={(event) =>
                      replaceDefinition(definitionForKind(event.target.value, definition))
                    }
                  >
                    {catalogue.kinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
                  </select>
                </label>
              ) : null}
              <fieldset>
                <legend className="text-sm">MITRE techniques (indicative)</legend>
                <div className="flex flex-wrap gap-2">
                  {catalogue.mitre.map((technique) => (
                    <label key={technique.id} className="inline-flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        aria-label={`MITRE ${technique.id}`}
                        disabled={!admin}
                        checked={definition.mitre.includes(technique.id)}
                        onChange={(event) =>
                          update({
                            mitre: event.target.checked
                              ? [...definition.mitre, technique.id]
                              : definition.mitre.filter((item) => item !== technique.id),
                          })
                        }
                      />
                      {technique.id} ({technique.name})
                    </label>
                  ))}
                </div>
              </fieldset>
            </section>

            <section className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
              <h2 className="font-semibold">What to match</h2>
              <fieldset>
                <legend className="text-sm">Event types</legend>
                <div className="flex flex-wrap gap-2">
                  {catalogue.event_types.map((type) => (
                    <label key={type} className="inline-flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        aria-label={`Event type ${type}`}
                        disabled={!admin}
                        checked={definition.match.event_types.includes(type)}
                        onChange={(event) =>
                          update({
                            match: {
                              ...definition.match,
                              event_types: event.target.checked
                                ? [...definition.match.event_types, type]
                                : definition.match.event_types.filter((item) => item !== type),
                            },
                          })
                        }
                      />
                      {type}
                    </label>
                  ))}
                </div>
              </fieldset>
              <ConditionBuilder
                value={definition.match.conditions}
                disabled={!admin}
                onChange={(conditions) =>
                  update({
                    match: { ...definition.match, conditions: conditions as { all: unknown[] } },
                  })
                }
              />
            </section>

            {definition.kind === "threshold" ? (
              <section className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
                <h2 className="font-semibold">Group and count</h2>
                <label className="text-sm">
                  Group by
                  <select
                    aria-label="Group by"
                    className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                    value={definition.group_by[0] ?? ""}
                    onChange={(event) => update({ group_by: event.target.value ? [event.target.value] : [] })}
                  >
                    <option value="">none (global)</option>
                    {catalogue.group_by.map((field) => <option key={field} value={field}>{field}</option>)}
                  </select>
                </label>
                <label className="text-sm">
                  Aggregate
                  <select
                    aria-label="Aggregate"
                    className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                    value={definition.aggregate.type}
                    onChange={(event) => update({ aggregate: { ...definition.aggregate, type: event.target.value } })}
                  >
                    <option value="count">count</option>
                    <option value="distinct_count">distinct count</option>
                  </select>
                </label>
                <label className="text-sm" htmlFor="rule-cooldown">
                  Cooldown (seconds)
                  <Input id="rule-cooldown" aria-label="Cooldown" type="number" className="ml-2 w-24" value={definition.cooldown_seconds} onChange={(event) => update({ cooldown_seconds: Number(event.target.value) })} />
                </label>
                <label className="text-sm">
                  Window mode
                  <select
                    aria-label="Window mode"
                    className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                    value={definition.window_mode}
                    onChange={(event) => update({ window_mode: event.target.value })}
                  >
                    <option value="sliding">sliding</option>
                    <option value="fixed">fixed</option>
                  </select>
                </label>
                {definition.window_mode === "fixed" ? (
                  <label className="text-sm">
                    Alignment
                    <select
                      aria-label="Fixed alignment"
                      className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                      value={definition.fixed_alignment ?? "minute"}
                      onChange={(event) => update({ fixed_alignment: event.target.value })}
                    >
                      <option value="minute">minute</option>
                      <option value="hour">hour</option>
                      <option value="day">day</option>
                    </select>
                  </label>
                ) : null}
                <p className="text-xs text-slate-500">
                  Sliding uses (t − window, t]; fixed uses UTC-aligned buckets.
                </p>
                <TierEditor
                  tiers={definition.tiers}
                  onChange={(tiers) => update({ tiers })}
                  match={definition.match}
                  max={catalogue.limits.max_tiers}
                  warnings={validation.warnings}
                  errors={serverErrors}
                  disabled={!admin}
                />
              </section>
            ) : null}

            {definition.kind === "sequence" ? (
              <section className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
                <h2 className="font-semibold">Steps</h2>
                {(definition.steps ?? []).map((step, index) => {
                  const match = step.match as { event_types?: string[] } | undefined;
                  return (
                    <div key={index} className="flex flex-wrap gap-2">
                      <Input
                        aria-label={`Step ${index + 1} event types`}
                        value={(match?.event_types ?? []).join(", ")}
                        readOnly={!admin}
                        onChange={(event) =>
                          update({
                            steps: definition.steps.map((item, position) =>
                              position === index
                                ? {
                                    ...item,
                                    match: {
                                      event_types: event.target.value.split(",").map((value) => value.trim()).filter(Boolean),
                                    },
                                  }
                                : item,
                            ),
                          })
                        }
                      />
                      <Input
                        aria-label={`Step ${index + 1} min count`}
                        type="number"
                        min={1}
                        value={Number(step.min_count ?? 1)}
                        readOnly={!admin}
                        onChange={(event) =>
                          update({
                            steps: definition.steps.map((item, position) =>
                              position === index ? { ...item, min_count: Number(event.target.value) } : item,
                            ),
                          })
                        }
                      />
                      <Input
                        aria-label={`Step ${index + 1} window seconds`}
                        type="number"
                        value={Number(step.window_seconds ?? 600)}
                        readOnly={!admin}
                        onChange={(event) =>
                          update({
                            steps: definition.steps.map((item, position) =>
                              position === index ? { ...item, window_seconds: Number(event.target.value) } : item,
                            ),
                          })
                        }
                      />
                    </div>
                  );
                })}
                <Button
                  disabled={!admin || (definition.steps?.length ?? 0) >= 5}
                  onClick={() =>
                    update({
                      steps: [
                        ...(definition.steps ?? []),
                        { match: { event_types: ["failed_login"] }, min_count: 1, window_seconds: 600 },
                      ],
                    })
                  }
                >
                  Add step
                </Button>
                <label className="text-sm">
                  Correlate on
                  <select
                    aria-label="Correlate on"
                    className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                    value={definition.correlate_on[0] ?? ""}
                    onChange={(event) => update({ correlate_on: event.target.value ? [event.target.value] : [] })}
                  >
                    <option value="">choose…</option>
                    {catalogue.group_by.map((field) => <option key={field} value={field}>{field}</option>)}
                  </select>
                </label>
                <Input aria-label="Within seconds" type="number" min={1} value={definition.within_seconds} readOnly={!admin} onChange={(event) => update({ within_seconds: Number(event.target.value) })} />
              </section>
            ) : null}
            {definition.kind === "new_value" ? (
              <section className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
                <h2 className="font-semibold">New value</h2>
                <Input aria-label="Field" value={definition.field ?? ""} readOnly={!admin} onChange={(event) => update({ field: event.target.value })} />
                <Input aria-label="Per entity field" value={definition.per ?? ""} readOnly={!admin} onChange={(event) => update({ per: event.target.value })} />
                <Input aria-label="Learning days" type="number" min={1} value={definition.learning_days} readOnly={!admin} onChange={(event) => update({ learning_days: Number(event.target.value) })} />
                <Input aria-label="Minimum history events" type="number" min={0} value={definition.min_history_events} readOnly={!admin} onChange={(event) => update({ min_history_events: Number(event.target.value) })} />
              </section>
            ) : null}
            {definition.kind === "baseline_metric" ? (
              <section className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
                <h2 className="font-semibold">Baseline metric</h2>
                <Input aria-label="Metric" value={definition.metric ?? ""} readOnly={!admin} onChange={(event) => update({ metric: event.target.value })} />
                <Input aria-label="Subject" value={definition.subject ?? ""} readOnly={!admin} onChange={(event) => update({ subject: event.target.value })} />
                <Input aria-label="Minimum standard deviation" type="number" step={0.1} value={definition.min_std} readOnly={!admin} onChange={(event) => update({ min_std: Number(event.target.value) })} />
                <Button
                  disabled={!admin || (definition.tiers?.length ?? 0) >= 10}
                  onClick={() => update({ tiers: [...definition.tiers, { label: "High", z: 3, min_absolute: 5, severity: "high", points: 20 } as unknown as TierLike] })}
                >
                  Add z-tier
                </Button>
                {(definition.tiers as unknown as Array<{ label: string; z: number; min_absolute: number; severity: string; points: number }>).map((tier, index) => (
                  <div key={index} className="flex flex-wrap gap-2">
                    <Input aria-label={`Z tier ${index + 1} z`} type="number" step={0.1} value={tier.z} readOnly={!admin} onChange={(event) => updateZ(index, { z: Number(event.target.value) })} />
                    <Input aria-label={`Z tier ${index + 1} minimum absolute`} type="number" value={tier.min_absolute} readOnly={!admin} onChange={(event) => updateZ(index, { min_absolute: Number(event.target.value) })} />
                    <select
                      aria-label={`Z tier ${index + 1} severity`}
                      className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                      value={tier.severity}
                      onChange={(event) => updateZ(index, { severity: event.target.value })}
                    >
                      {["low", "medium", "high", "critical"].map((severity) => <option key={severity} value={severity}>{severity}</option>)}
                    </select>
                  </div>
                ))}
              </section>
            ) : null}
            {definition.kind === "incident_meta" ? (
              <section className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
                <h2 className="font-semibold">Incident meta conditions</h2>
                {(definition.meta_conditions ?? []).map((condition, index) => (
                  <div key={index} className="flex flex-wrap gap-2">
                    <select
                      aria-label={`Meta condition ${index + 1} metric`}
                      className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                      value={condition.metric}
                      onChange={(event) => update({ meta_conditions: definition.meta_conditions.map((item, position) => position === index ? { ...item, metric: event.target.value } : item) })}
                    >
                      {["distinct_event_types", "distinct_rules_fired", "event_count", "has_strong_links_only", "span_minutes", "weak_link_ratio"].map((metric) => <option key={metric} value={metric}>{metric}</option>)}
                    </select>
                    <select
                      aria-label={`Meta condition ${index + 1} operator`}
                      className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                      value={condition.op}
                      onChange={(event) => update({ meta_conditions: definition.meta_conditions.map((item, position) => position === index ? { ...item, op: event.target.value } : item) })}
                    >
                      {["gte", "lte", "eq", "ne", "gt", "lt"].map((op) => <option key={op} value={op}>{op}</option>)}
                    </select>
                    <Input aria-label={`Meta condition ${index + 1} value`} type="number" value={condition.value} readOnly={!admin} onChange={(event) => update({ meta_conditions: definition.meta_conditions.map((item, position) => position === index ? { ...item, value: Number(event.target.value) } : item) })} />
                  </div>
                ))}
                <Button
                  disabled={!admin || (definition.meta_conditions?.length ?? 0) >= 5}
                  onClick={() => update({ meta_conditions: [...(definition.meta_conditions ?? []), { metric: "event_count", op: "gte", value: 5 }] })}
                >
                  Add meta condition
                </Button>
              </section>
            ) : null}
            {definition.kind === "field_match" ? (
              <p className="text-sm text-slate-600 dark:text-slate-300">
                This kind uses the condition builder above; every condition is validated by the server.
              </p>
            ) : null}

            <section className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
              <h2 className="font-semibold">Actions</h2>
              <label className="inline-flex items-center gap-1 text-sm">
                <input type="checkbox" aria-label="Create incident" checked={definition.actions.create_incident} disabled={!admin} onChange={(event) => update({ actions: { ...definition.actions, create_incident: event.target.checked } })} />
                Create incident
              </label>
              <label className="inline-flex items-center gap-1 text-sm">
                <input type="checkbox" aria-label="Notify" checked={definition.actions.notify} disabled={!admin} onChange={(event) => update({ actions: { ...definition.actions, notify: event.target.checked } })} />
                Notify
              </label>
              <label className="inline-flex items-center gap-1 text-sm">
                <input type="checkbox" aria-label="Exclude allowlisted" checked={definition.scope.exclude_allowlisted} disabled={!admin} onChange={(event) => update({ scope: { exclude_allowlisted: event.target.checked } })} />
                Exclude allowlisted events
              </label>
            </section>
          </div>
          <div className="space-y-4">
            <PreviewPanel result={preview} loading={previewLoading} onRangeChange={setRange} />
            {admin ? <Button onClick={confirmSave}>Save rule</Button> : null}
            {id ? (
              <VersionHistory
                versions={versions}
                onRestore={(version) => {
                  if (!admin) return;
                  setRestoreVersion(version);
                }}
              />
            ) : null}
          </div>
        </div>
      )}

      {diffs ? (
        <SaveDiffDialog
          diffs={diffs}
          warning={highImpact ? `This change would produce ${preview?.total_findings} findings in the selected range. Review before saving.` : null}
          onConfirm={() => void save()}
          onCancel={() => setDiffs(null)}
        />
      ) : null}
      {restoreVersion !== null && id ? (
        <ConfirmDialog
          title={`Restore version ${restoreVersion}?`}
          onCancel={() => setRestoreVersion(null)}
          onConfirm={() => {
            void client
              .POST("/api/rules/{identifier}/versions/{version}/restore", {
                params: { path: { identifier: id, version: restoreVersion } },
              })
              .then(() => {
                show("Version restored", "success");
                setRestoreVersion(null);
                router.refresh();
              })
              .catch(() => show("Could not restore the version"));
          }}
        />
      ) : null}
    </div>
  );
}

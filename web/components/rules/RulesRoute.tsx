"use client";

import { useRef, useState } from "react";

import { RulesList, type RuleRow, type RulesFilters } from "@/components/rules/RulesList";
import { Card, ConfirmDialog, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { ApiError, client } from "@/lib/api/client";
import { useApiList } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";
import { ruleSummary } from "@/lib/rules/helpers";

const emptyFilters: RulesFilters = { kind: "", enabled: null, search: "", builtin: null, noisy: false };

export function RulesRoute() {
  const [filters, setFilters] = useState<RulesFilters>(emptyFilters);
  const [confirm, setConfirm] = useState<{ action: "delete" | "reset"; id: string } | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const me = useMe();
  const { show } = useToast();
  const query = useApiList<Record<string, unknown>>("/api/rules");
  const findings = useApiList<Record<string, unknown>>("/api/rules/findings");
  const rows: RuleRow[] = (query.data?.items ?? []).map((item) => {
    const rule = item as unknown as Parameters<typeof ruleSummary>[0];
    const related = (findings.data?.items ?? []).filter(
      (finding) => finding.rule_id === item.id,
    );
    return {
      id: String(item.id),
      name: String(item.name ?? item.id),
      enabled: Boolean(item.enabled),
      kind: String(item.kind ?? "threshold"),
      summary: ruleSummary(rule),
      builtin: Boolean(item.builtin ?? item.default_definition_json),
      modified: Boolean(item.modified),
      version: Number(item.version ?? 1),
      tier_severities: Array.isArray(item.tiers)
        ? (item.tiers as Array<{ severity: string }>).map((tier) => tier.severity)
        : [],
      findings_24h: related.length,
      findings_7d: related.length,
    };
  }).filter((row) => {
    if (filters.kind && row.kind !== filters.kind) return false;
    if (filters.enabled !== null && row.enabled !== filters.enabled) return false;
    if (filters.search && !row.name.toLowerCase().includes(filters.search.toLowerCase())) return false;
    return true;
  });

  const mutate = async (path: string, body?: unknown) => {
    try {
      await client.POST(path as never, (body ?? {}) as never);
      void query.refetch();
    } catch (cause) {
      show(cause instanceof ApiError ? cause.message : "Action failed");
    }
  };

  return (
    <Card>
      {query.isLoading ? <Skeleton rows={5} /> : query.isError ? (
        <ErrorState message="Could not load rules." onRetry={() => void query.refetch()} />
      ) : (
        <>
          <input
            ref={file}
            type="file"
            accept="application/json"
            className="hidden"
            aria-label="Import rules file"
            onChange={(event) => {
              const selected = event.target.files?.[0];
              if (!selected) return;
              void selected.text().then(async (text) => {
                try {
                  const rules = JSON.parse(text) as unknown[];
                  const response = await client.POST("/api/rules/import", { body: { rules } });
                  const body = response.data as { errors?: Array<{ path: string; message: string }> } | undefined;
                  if (body?.errors?.length) {
                    show(body.errors.map((error) => `${error.path}: ${error.message}`).join("; "));
                  } else {
                    show("Rules imported", "success");
                  }
                  void query.refetch();
                } catch {
                  show("Invalid JSON file");
                }
              });
            }}
          />
          <RulesList
            rules={rows}
            filters={filters}
            onFiltersChange={setFilters}
            onToggle={(id, enabled) => void mutate(`/api/rules/${id}/${enabled ? "enable" : "disable"}`)}
            onDuplicate={(id) => {
              void client
                .GET("/api/rules/{identifier}", { params: { path: { identifier: id } } })
                .then(({ data }) => {
                  if (!data) return;
                  const definition = data as Record<string, unknown>;
                  const nextId = `${id}-copy-${Date.now()}`;
                  return client.POST("/api/rules", {
                    body: { definition: { ...definition, id: nextId, name: `${String(definition.name)} copy` } },
                  });
                })
                .then(() => {
                  void query.refetch();
                  show("Rule duplicated", "success");
                })
                .catch(() => show("Could not duplicate the rule"));
            }}
            onReset={(id) => setConfirm({ action: "reset", id })}
            onDelete={(id) => setConfirm({ action: "delete", id })}
            onImport={() => file.current?.click()}
            onExport={() => {
              const blob = new Blob([JSON.stringify(query.data?.items ?? [], null, 2)], { type: "application/json" });
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement("a");
              anchor.href = url;
              anchor.download = "sentinel-rules.json";
              anchor.click();
              URL.revokeObjectURL(url);
            }}
            currentRole={me.role}
          />
          {confirm ? (
            <ConfirmDialog
              title={confirm.action === "delete" ? "Delete this rule?" : "Reset this rule to default?"}
              confirmPhrase={confirm.action === "delete" ? confirm.id : undefined}
              onCancel={() => setConfirm(null)}
              onConfirm={() => {
                const action = confirm.action;
                const target = confirm.id;
                setConfirm(null);
                if (action === "reset") {
                  void mutate(`/api/rules/${target}/reset`);
                } else {
                  void client
                    .DELETE("/api/rules/{identifier}", { params: { path: { identifier: target } } })
                    .then(() => void query.refetch())
                    .catch(() => show("Could not delete the rule"));
                }
              }}
            />
          ) : null}
        </>
      )}
    </Card>
  );
}

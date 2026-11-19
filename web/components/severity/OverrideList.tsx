"use client";

import { useState } from "react";

import { ConditionBuilder } from "@/components/conditions/ConditionBuilder";
import { Button, Input } from "@/components/ui/primitives";
import type { Role } from "@/lib/auth";

export interface OverrideRow {
  id: number;
  name: string;
  enabled?: boolean;
  builtin?: boolean;
  modified?: boolean;
  severity?: string;
  conditions?: unknown;
}

export function OverrideList({
  overrides,
  onReorder,
  currentRole,
  onUpdate,
  onDelete,
  onReset,
  onTest,
  onCreate,
  onDuplicate,
}: {
  overrides: OverrideRow[];
  onReorder: (ids: number[]) => void;
  currentRole: Role;
  onUpdate?: (override: OverrideRow, changes: Partial<OverrideRow>) => void;
  onDelete?: (id: number) => void;
  onReset?: (id: number) => void;
  onTest?: (sample: string) => void;
  onCreate?: () => void;
  onDuplicate?: (id: number) => void;
}) {
  const ids = overrides.map((item) => item.id);
  const [dragged, setDragged] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [sample, setSample] = useState("");
  const move = (index: number, direction: -1 | 1) => {
    const next = [...ids];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target]!, next[index]!];
    onReorder(next);
  };

  return (
    <section aria-label="Severity overrides" className="space-y-2">
      <div className="flex items-center gap-2">
        <h2 className="mr-auto font-semibold">Overrides (first match wins)</h2>
        <Button disabled={currentRole !== "admin"} onClick={() => onCreate?.()}>Create override</Button>
      </div>
      <p className="text-xs text-slate-500">
        Overrides are evaluated in order; the first match wins. Reorder by dragging or with the
        keyboard-accessible arrows.
      </p>
      <ol className="space-y-2" aria-label="Override priority">
        {overrides.map((override, index) => (
          <li
            key={override.id}
            draggable={currentRole === "admin"}
            onDragStart={() => setDragged(override.id)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => {
              if (dragged === null || dragged === override.id) return;
              const next = ids.filter((id) => id !== dragged);
              next.splice(index, 0, dragged);
              onReorder(next);
              setDragged(null);
            }}
            className="rounded border border-slate-200 p-2 text-sm dark:border-slate-700"
          >
            <div className="flex items-center gap-2">
              <span className="tabular-nums">{index + 1}</span>
              <span className="mr-auto">
                {override.name}
                {override.builtin ? <span className="ml-2 text-xs">built-in</span> : null}
                {override.modified ? <span className="ml-2 text-xs text-amber-800">modified</span> : null}
              </span>
              <select
                aria-label={`Severity for override ${override.id}`}
                disabled={currentRole !== "admin"}
                className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                value={override.severity ?? "low"}
                onChange={(event) => onUpdate?.(override, { severity: event.target.value })}
              >
                {["low", "medium", "high", "critical"].map((severity) => (
                  <option key={severity} value={severity}>{severity}</option>
                ))}
              </select>
              <Button disabled={currentRole !== "admin"} onClick={() => move(index, -1)} aria-label="Move up">↑</Button>
              <Button disabled={currentRole !== "admin"} onClick={() => move(index, 1)} aria-label="Move down">↓</Button>
              <Button onClick={() => setExpanded(expanded === override.id ? null : override.id)}>
                {expanded === override.id ? "Hide conditions" : "Edit conditions"}
              </Button>
              {override.builtin && onReset ? (
                <Button disabled={currentRole !== "admin"} onClick={() => onReset(override.id)}>Reset</Button>
              ) : null}
              {onDuplicate && !override.builtin ? (
                <Button disabled={currentRole !== "admin"} onClick={() => onDuplicate(override.id)}>Duplicate</Button>
              ) : null}
              {onDelete && !override.builtin ? (
                <Button disabled={currentRole !== "admin"} onClick={() => onDelete(override.id)}>Delete</Button>
              ) : null}
            </div>
            {expanded === override.id ? (
              <ConditionBuilder
                value={override.conditions ?? { all: [] }}
                disabled={currentRole !== "admin"}
                onChange={(conditions) => onUpdate?.(override, { conditions })}
              />
            ) : null}
          </li>
        ))}
      </ol>
      {onTest ? (
        <div className="rounded border border-slate-200 p-3 dark:border-slate-700">
          <h3 className="font-semibold">Test an event</h3>
          <Input aria-label="Override test event" value={sample} onChange={(event) => setSample(event.target.value)} placeholder="Paste a JSON event or pick one from recent events" />
          <Button className="mt-2" onClick={() => onTest(sample)}>Test</Button>
        </div>
      ) : null}
    </section>
  );
}

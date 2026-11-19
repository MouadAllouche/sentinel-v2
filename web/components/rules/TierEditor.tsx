"use client";

import { Button } from "@/components/ui/primitives";
import { secondsToWindow, tierSentence, windowToSeconds, type TierLike, type WindowUnit } from "@/lib/rules/helpers";

const SEVERITIES = ["low", "medium", "high", "critical"];
const UNITS: WindowUnit[] = ["seconds", "minutes", "hours", "days"];

export function TierEditor({
  tiers,
  onChange,
  match,
  max = 10,
  errors = [],
  warnings = [],
  disabled = false,
}: {
  tiers: TierLike[];
  onChange: (tiers: TierLike[]) => void;
  match: { event_types?: string[]; group_by?: string[] };
  max?: number;
  errors?: string[];
  warnings?: string[];
  disabled?: boolean;
}) {
  const update = (index: number, changes: Partial<TierLike>) =>
    onChange(tiers.map((tier, position) => (position === index ? { ...tier, ...changes } : tier)));
  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= tiers.length) return;
    const next = [...tiers];
    [next[index], next[target]] = [next[target]!, next[index]!];
    onChange(next);
  };

  return (
    <section aria-label="Tiers" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Tiers</h2>
        <Button
          onClick={() =>
            onChange([...tiers, { label: `Tier ${tiers.length + 1}`, count: 5, window_seconds: 600, severity: "medium", points: 0 }])
          }
          aria-label="Add tier"
          disabled={disabled || tiers.length >= max}
        >
          Add tier
        </Button>
      </div>
      {tiers.map((tier, index) => {
        const window = secondsToWindow(tier.window_seconds);
        return (
          <div key={index} className="rounded border border-slate-200 p-3 dark:border-slate-700">
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs">
                Label
                <input
                  aria-label={`Tier ${index + 1} label`}
                  disabled={disabled}
                  className="ml-1 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                  value={tier.label ?? ""}
                  onChange={(event) => update(index, { label: event.target.value })}
                />
              </label>
              <label className="text-xs">
                Count ≥
                <input
                  type="number"
                  min={1}
                  aria-label={`Tier ${index + 1} count`}
                  disabled={disabled}
                  className="ml-1 w-24 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                  value={tier.count}
                  onChange={(event) => update(index, { count: Number(event.target.value) })}
                />
              </label>
              <label className="text-xs">
                Window
                <input
                  type="number"
                  min={1}
                  aria-label={`Tier ${index + 1} window`}
                  disabled={disabled}
                  className="ml-1 w-20 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                  value={window.value}
                  onChange={(event) =>
                    update(index, { window_seconds: windowToSeconds(Number(event.target.value), window.unit) })
                  }
                />
                <select
                  aria-label={`Tier ${index + 1} window unit`}
                  disabled={disabled}
                  className="ml-1 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                  value={window.unit}
                  onChange={(event) =>
                    update(index, { window_seconds: windowToSeconds(window.value, event.target.value as WindowUnit) })
                  }
                >
                  {UNITS.map((unit) => <option key={unit} value={unit}>{unit}</option>)}
                </select>
              </label>
              <label className="text-xs">
                Severity
                <select
                  aria-label={`Tier ${index + 1} severity`}
                  disabled={disabled}
                  className="ml-1 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                  value={tier.severity}
                  onChange={(event) => update(index, { severity: event.target.value })}
                >
                  {SEVERITIES.map((severity) => <option key={severity} value={severity}>{severity}</option>)}
                </select>
              </label>
              <label className="text-xs">
                Points
                <input
                  type="number"
                  min={0}
                  max={100}
                  aria-label={`Tier ${index + 1} points`}
                  disabled={disabled}
                  className="ml-1 w-20 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
                  value={tier.points ?? 0}
                  onChange={(event) => update(index, { points: Number(event.target.value) })}
                />
              </label>
              <Button onClick={() => move(index, -1)} disabled={disabled || index === 0} aria-label="Move up">↑</Button>
              <Button onClick={() => move(index, 1)} disabled={disabled || index === tiers.length - 1} aria-label="Move down">↓</Button>
              <Button onClick={() => onChange(tiers.filter((_, position) => position !== index))} disabled={disabled} aria-label="Remove tier">
                Remove tier
              </Button>
            </div>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{tierSentence(tier, match)}</p>
          </div>
        );
      })}
      {warnings.map((warning, index) => (
        <p key={index} role="status" className="text-sm text-amber-800 dark:text-amber-200">{warning}</p>
      ))}
      {errors.map((error, index) => (
        <p key={index} role="alert" className="text-sm text-red-700">{error}</p>
      ))}
    </section>
  );
}

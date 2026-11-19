"use client";

import { useState } from "react";

import { whatIfScore, type ScoreReason } from "@/lib/incident/helpers";

export function WhatIfPanel({
  reasons,
  thresholds,
}: {
  reasons: ScoreReason[];
  thresholds?: { medium: number; high: number; critical: number };
}) {
  const [disabled, setDisabled] = useState<string[]>([]);
  const bands = thresholds ?? { medium: 50, high: 75, critical: 75 };
  const result = whatIfScore(reasons, bands, disabled);
  const ruleIds = reasons.filter((reason) => reason.rule_id).map((reason) => reason.rule_id!);
  const unique = [...new Set(ruleIds)];

  return (
    <section aria-label="What-if score simulation" className="rounded border border-slate-200 p-3 dark:border-slate-700">
      <h2 className="font-semibold">What if rules were disabled?</h2>
      <p className="text-xs text-slate-500">Simulation, not saved.</p>
      <div className="mt-2 flex flex-wrap gap-3">
        {unique.map((ruleId) => (
          <label key={ruleId} className="inline-flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              aria-label={ruleId}
              checked={disabled.includes(ruleId)}
              onChange={() =>
                setDisabled((current) =>
                  current.includes(ruleId)
                    ? current.filter((item) => item !== ruleId)
                    : [...current, ruleId],
                )
              }
            />
            {ruleId}
          </label>
        ))}
      </div>
      <p data-testid="what-if-score" className="mt-2 text-sm">
        Simulated score: <strong className="tabular-nums">{result.score}</strong> ({result.severity})
      </p>
    </section>
  );
}

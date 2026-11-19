"use client";

import { useState } from "react";

import { Button, Input } from "@/components/ui/primitives";
import type { Role } from "@/lib/auth";

export function ReapplyPanel({
  preview,
  onPreview,
  onApply,
  currentRole,
}: {
  preview: { changed: number; by_severity?: Record<string, number> } | null;
  onPreview: () => void;
  onApply: () => void;
  currentRole: Role;
}) {
  const [confirmation, setConfirmation] = useState("");
  return (
    <section aria-label="Apply to existing events" className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
      <h2 className="font-semibold">Apply to existing events</h2>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Changes affect new events only. Preview the impact before re-applying to stored events.
      </p>
      <Button onClick={onPreview} disabled={currentRole !== "admin"}>Preview re-apply</Button>
      {preview ? (
        <p role="status" className="text-sm">
          {preview.changed} events would change severity.
        </p>
      ) : null}
      {currentRole === "admin" ? (
        <div className="flex flex-wrap items-center gap-2">
          <Input
            aria-label="Type confirm"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            placeholder="Type confirm"
          />
          <Button
            disabled={!preview || confirmation !== "confirm"}
            onClick={onApply}
          >
            Apply to existing events
          </Button>
        </div>
      ) : null}
    </section>
  );
}

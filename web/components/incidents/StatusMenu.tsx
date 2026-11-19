"use client";

import { useState } from "react";

import { Button, Input, Label } from "@/components/ui/primitives";
import { allowedTransitions, REASON_REQUIRED } from "@/lib/incident/helpers";
import type { Role } from "@/lib/auth";

export function StatusMenu({
  status,
  currentRole,
  onChange,
  error,
}: {
  status: string;
  currentRole: Role;
  onChange: (status: string, reason?: string) => void;
  error?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  if (currentRole !== "admin") return null;

  const choose = (next: string) => {
    if (REASON_REQUIRED.has(next)) {
      setTarget(next);
      return;
    }
    onChange(next);
    setOpen(false);
  };

  return (
    <div className="relative">
      <Button onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        Change status
      </Button>
      {open ? (
        <div role="menu" className="absolute z-20 mt-1 rounded border border-slate-300 bg-white p-2 shadow dark:border-slate-600 dark:bg-slate-900">
          {allowedTransitions(status).length === 0 ? (
            <p className="text-sm text-slate-500">No transitions are available.</p>
          ) : (
            allowedTransitions(status).map((next) => (
              <button
                key={next}
                type="button"
                role="menuitem"
                className="block w-full px-2 py-1 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => choose(next)}
              >
                {next.replaceAll("_", " ")}
              </button>
            ))
          )}
        </div>
      ) : null}
      {target ? (
        <div role="dialog" aria-modal="true" aria-label="Change status reason" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded bg-white p-4 dark:bg-slate-900">
            <h2 className="font-semibold">Reason for {target.replaceAll("_", " ")}</h2>
            <Label htmlFor="status-reason">Reason</Label>
            <Input id="status-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
            <div className="mt-3 flex justify-end gap-2">
              <Button onClick={() => setTarget(null)}>Cancel</Button>
              <Button
                disabled={reason.trim().length === 0}
                onClick={() => {
                  onChange(target, reason);
                  setTarget(null);
                  setOpen(false);
                  setReason("");
                }}
              >
                Confirm
              </Button>
            </div>
          </div>
        </div>
      ) : null}
      {error === "conflict" ? (
        <p role="alert" className="mt-1 text-sm text-red-700">Incident changed, reload</p>
      ) : null}
    </div>
  );
}

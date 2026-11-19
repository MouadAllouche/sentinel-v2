"use client";

import { useState } from "react";

import { Button, Input, Label } from "@/components/ui/primitives";

export interface AllowlistPayload {
  kind: string;
  value: string;
  scope: string;
  reason: string;
  expires_at: string | null;
}

export function AllowlistDialog({
  onSave,
  onCancel,
}: {
  onSave: (payload: AllowlistPayload) => void;
  onCancel: () => void;
}) {
  const [kind, setKind] = useState("ip");
  const [value, setValue] = useState("");
  const [scope, setScope] = useState("annotate");
  const [reason, setReason] = useState("");
  const [expiry, setExpiry] = useState("7d");
  const validValue = value.trim().length > 0 && reason.trim().length >= 5;

  return (
    <div role="dialog" aria-modal="true" aria-label="Allowlist entry" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md space-y-3 rounded bg-white p-4 dark:bg-slate-900">
        <h2 className="text-lg font-semibold">New allowlist entry</h2>
        <p className="text-xs text-slate-500">
          Allowlisted evidence is still stored and shown; it is excluded from alerts/incidents only
          when scope is <em>suppress alerts</em>.
        </p>
        <Label htmlFor="allow-kind">Kind</Label>
        <select
          id="allow-kind"
          aria-label="Allowlist kind"
          className="w-full rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
          value={kind}
          onChange={(event) => setKind(event.target.value)}
        >
          {["ip", "cidr", "username", "command", "event_type", "path"].map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
        <Label htmlFor="allow-value">Value</Label>
        <Input id="allow-value" aria-label="Allowlist value" value={value} onChange={(event) => setValue(event.target.value)} />
        <Label htmlFor="allow-scope">Scope</Label>
        <select
          id="allow-scope"
          aria-label="Allowlist scope"
          className="w-full rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
          value={scope}
          onChange={(event) => setScope(event.target.value)}
        >
          <option value="annotate">annotate only</option>
          <option value="suppress_alerts">suppress alerts</option>
          <option value="lower_severity">lower severity</option>
        </select>
        <Label htmlFor="allow-reason">Reason</Label>
        <Input id="allow-reason" aria-label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
        <Label htmlFor="allow-expiry">Expiry</Label>
        <select
          id="allow-expiry"
          aria-label="Expiry"
          className="w-full rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
          value={expiry}
          onChange={(event) => setExpiry(event.target.value)}
        >
          <option value="1d">1 day</option>
          <option value="7d">7 days</option>
          <option value="30d">30 days</option>
          <option value="never">never</option>
        </select>
        {expiry === "never" ? (
          <p role="status" className="text-sm text-amber-800 dark:text-amber-200">
            never expires — review this entry regularly.
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button onClick={onCancel}>Cancel</Button>
          <Button
            disabled={!validValue}
            onClick={() =>
              onSave({
                kind,
                value,
                scope,
                reason,
                expires_at:
                  expiry === "never"
                    ? null
                    : new Date(
                        Date.now() + Number(expiry.slice(0, -1)) * 86400000,
                      ).toISOString(),
              })
            }
          >
            Save entry
          </Button>
        </div>
      </div>
    </div>
  );
}

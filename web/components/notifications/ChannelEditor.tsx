"use client";

import { useState } from "react";

import { Button, Input, Label } from "@/components/ui/primitives";
import { validateEnvName } from "@/lib/admin/helpers";

export interface ChannelValue {
  name: string;
  kind: string;
  enabled: boolean;
  config: Record<string, unknown>;
  min_severity?: string;
}

export function ChannelEditor({
  value,
  envVars,
  onSave,
  readOnly = false,
}: {
  value: ChannelValue;
  envVars: Record<string, boolean>;
  onSave: (value: ChannelValue) => void;
  readOnly?: boolean;
}) {
  const [draft, setDraft] = useState<ChannelValue>(value);
  const secretKey = draft.kind === "email" ? "password_env" : draft.kind === "telegram" ? "token_env" : "secret_env";
  const secretName = String(draft.config[secretKey] ?? "");
  const secretError = secretName ? validateEnvName(secretName) : null;

  return (
    <section aria-label="Notification channel editor" className="space-y-3 rounded border border-slate-200 p-3 dark:border-slate-700">
      <p className="text-sm text-amber-800 dark:text-amber-200">
        Sentinel will send incident titles and severities to this destination.
      </p>
      <Label htmlFor="channel-name">Name</Label>
      <Input id="channel-name" aria-label="Channel name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
      <Label htmlFor="channel-kind">Kind</Label>
      <select
        id="channel-kind"
        aria-label="Channel kind"
        className="w-full rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
        value={draft.kind}
        onChange={(event) => setDraft({ ...draft, kind: event.target.value })}
      >
        {["webhook", "email", "telegram"].map((kind) => <option key={kind} value={kind}>{kind}</option>)}
      </select>
      <Label htmlFor="secret-env">Secret env var</Label>
      <Input
        id="secret-env"
        aria-label="Secret env var"
        value={secretName}
        onChange={(event) => setDraft({ ...draft, config: { ...draft.config, [secretKey]: event.target.value } })}
        aria-invalid={Boolean(secretError)}
      />
      {secretError ? <p role="alert" className="text-sm text-red-700">{secretError}</p> : null}
      <p role="status" className="text-sm">
        {secretName && envVars[secretName] ? "set" : "not set"}
      </p>
      <Button disabled={readOnly || Boolean(secretError)} onClick={() => onSave(draft)}>Save channel</Button>
    </section>
  );
}

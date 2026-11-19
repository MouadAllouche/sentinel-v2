"use client";

import { useState } from "react";

import { Button, Card, Input, Label } from "@/components/ui/primitives";
import type { Role } from "@/lib/auth";

export interface DriftPath {
  id: number;
  path: string;
  kind: string;
  enabled: boolean;
  sensitivity: string;
  category: string;
  metadata_only: boolean;
  baseline_status: string;
  last_checked?: string;
  last_change?: string;
  warnings?: string[];
}

export interface DriftSnapshotView {
  id: number;
  path: string;
  mode?: string;
  owner?: string;
  group?: string;
  size?: number;
  mtime?: string;
  hash_prefix?: string;
  flags?: string[];
  at?: string;
}

export function DriftPage({
  paths,
  snapshots,
  onSelect,
  onAccept,
  onCheck,
  role,
}: {
  paths: DriftPath[];
  snapshots: DriftSnapshotView[];
  onSelect: (path: DriftPath) => void;
  onAccept: (id: number, reason: string) => void;
  onCheck: () => void;
  role: Role;
}) {
  const [selected, setSelected] = useState<DriftPath | null>(null);
  const [reason, setReason] = useState("");
  const admin = role === "admin";

  return (
    <div className="space-y-4">
      <div role="note" className="rounded border border-blue-300 bg-blue-50 p-3 text-sm dark:border-blue-700 dark:bg-blue-950">
        Sentinel only observes; it never modifies monitored files.
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Configuration drift</h1>
        <Button disabled={!admin} onClick={onCheck}>Check now</Button>
      </div>
      <Card>
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Monitored paths</caption>
          <thead>
            <tr>
              <th scope="col">Path</th><th scope="col">Kind</th><th scope="col">Sensitivity</th>
              <th scope="col">Category</th><th scope="col">Enabled</th><th scope="col">Metadata only</th>
              <th scope="col">Baseline</th><th scope="col">Last checked</th><th scope="col">Warnings</th>
            </tr>
          </thead>
          <tbody>
            {paths.map((path) => (
              <tr key={path.id} className="cursor-pointer border-b border-slate-100 dark:border-slate-800" onClick={() => {
                setSelected(path);
                onSelect(path);
              }}>
                <td className="font-mono text-xs">{path.path}</td>
                <td>{path.kind}</td>
                <td>{path.sensitivity}</td>
                <td>{path.category}</td>
                <td>{path.enabled ? "enabled" : "disabled"}</td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Metadata only for ${path.path}`}
                    checked={path.metadata_only}
                    disabled
                    readOnly
                  />
                </td>
                <td><span className={path.baseline_status === "drifted" ? "text-red-700" : "text-emerald-700"}>{path.baseline_status}</span></td>
                <td>{path.last_checked ?? "—"}</td>
                <td>{path.warnings?.join("; ") ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {selected ? (
        <Card>
          <h2 className="font-semibold">Path detail: {selected.path}</h2>
          <p className="mt-1 text-xs text-slate-500">
            Metadata only — hashes are shown as prefixes; file contents are never stored or displayed.
          </p>
          <table className="mt-2 w-full text-left text-sm">
            <caption className="sr-only">Snapshot metadata</caption>
            <thead><tr><th scope="col">When</th><th scope="col">Mode</th><th scope="col">Owner</th><th scope="col">Hash prefix</th><th scope="col">Flags</th></tr></thead>
            <tbody>
              {snapshots.map((item) => (
                <tr key={item.id}>
                  <td>{item.at ?? "—"}</td><td>{item.mode ?? "—"}</td><td>{item.owner ?? "—"}</td>
                  <td>{item.hash_prefix ?? "—"}</td><td>{item.flags?.join(", ") ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {admin ? (
            <div className="mt-3 space-y-2">
              <Label htmlFor="accept-reason">Reason</Label>
              <Input id="accept-reason" aria-label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
              <Button
                onClick={() => setReason("__open__")}
                aria-label="Accept as new baseline"
              >
                Accept as new baseline
              </Button>
              {reason === "__open__" ? (
                <div role="dialog" aria-modal="true" aria-label="Accept baseline" className="rounded border border-slate-300 p-3">
                  <p className="text-sm">
                    This only updates Sentinel&apos;s reference. It never changes the monitored file.
                  </p>
                  <Input aria-label="Baseline reason" value={reason === "__open__" ? "" : reason} onChange={(event) => setReason(event.target.value)} placeholder="Reason" />
                  <div className="mt-2 flex gap-2">
                    <Button onClick={() => setReason("")}>Cancel</Button>
                    <Button disabled={reason.length === 0 || reason === "__open__"} onClick={() => {
                      onAccept(selected.id, reason);
                      setReason("");
                    }}>Confirm</Button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}

"use client";

import { Button } from "@/components/ui/primitives";
import type { DiffEntry } from "@/lib/rules/helpers";

export function SaveDiffDialog({
  diffs,
  warning,
  onConfirm,
  onCancel,
}: {
  diffs: DiffEntry[];
  warning?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div role="dialog" aria-modal="true" aria-label="Review rule changes" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-xl rounded bg-white p-4 dark:bg-slate-900">
        <h2 className="text-lg font-semibold">Review changes</h2>
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">Before and after values</caption>
          <thead><tr><th scope="col">Field</th><th scope="col">Before</th><th scope="col">After</th></tr></thead>
          <tbody>
            {diffs.map((diff) => (
              <tr key={diff.path} className="border-b border-slate-100 dark:border-slate-800">
                <th scope="row">{diff.path}</th>
                <td>{JSON.stringify(diff.before)}</td>
                <td>{JSON.stringify(diff.after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {warning ? (
          <p role="alert" className="mt-2 rounded border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
            {warning}
          </p>
        ) : null}
        <div className="mt-3 flex justify-end gap-2">
          <Button onClick={onCancel}>Cancel</Button>
          <Button onClick={onConfirm}>Confirm</Button>
        </div>
      </div>
    </div>
  );
}

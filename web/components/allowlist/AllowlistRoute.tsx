"use client";

import { useState } from "react";

import { AllowlistDialog, type AllowlistPayload } from "@/components/allowlist/AllowlistDialog";
import { Button, Card, ConfirmDialog, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { client } from "@/lib/api/client";
import { useApiList } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";

export function AllowlistRoute() {
  const [open, setOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const me = useMe();
  const { show } = useToast();
  const query = useApiList<Record<string, unknown>>("/api/allowlist");
  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Allowlist</h1>
        {me.role === "admin" ? <Button onClick={() => setOpen(true)}>New entry</Button> : <span className="text-sm text-slate-500">View only</span>}
      </div>
      <p role="note" className="mb-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-700 dark:bg-amber-950">
        Allowlisted evidence is still stored and shown; it is excluded from alerts/incidents only when
        scope is <em>suppress alerts</em>.
      </p>
      {query.isLoading ? <Skeleton rows={4} /> : query.isError ? (
        <ErrorState message="Could not load the allowlist." onRetry={() => void query.refetch()} />
      ) : (
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Allowlist entries</caption>
          <thead>
            <tr>
              <th scope="col">Kind</th><th scope="col">Value</th><th scope="col">Scope</th>
              <th scope="col">Reason</th><th scope="col">Expires</th><th scope="col">Matches 24h</th>
              {me.role === "admin" ? <th scope="col">Action</th> : null}
            </tr>
          </thead>
          <tbody>
            {(query.data?.items ?? []).map((item, index) => (
              <tr key={Number(item.id ?? index)} className="border-b border-slate-100 dark:border-slate-800">
                <td>{String(item.kind ?? "—")}</td>
                <td>{String(item.value ?? "—")}</td>
                <td>{String(item.scope ?? "—")}</td>
                <td>{String(item.reason ?? "—")}</td>
                <td>{String(item.expires_at ?? "never")}</td>
                <td>{Number(item.matches_24h ?? 0)}</td>
                {me.role === "admin" ? (
                  <td>
                    <Button onClick={() => setPendingDelete(Number(item.id))}>Delete</Button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {pendingDelete !== null ? (
        <ConfirmDialog
          title="Delete this allowlist entry?"
          confirmPhrase={String(pendingDelete)}
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            const identifier = pendingDelete;
            setPendingDelete(null);
            void client
              .DELETE("/api/allowlist/{identifier}", { params: { path: { identifier } } })
              .then(() => void query.refetch())
              .catch(() => show("Could not delete the entry"));
          }}
        />
      ) : null}
      {open ? (
        <AllowlistDialog
          onCancel={() => setOpen(false)}
          onSave={(payload: AllowlistPayload) => {
            void client.POST("/api/allowlist", { body: payload as unknown as Record<string, unknown> })
              .then(() => {
                setOpen(false);
                void query.refetch();
                show("Allowlist entry added", "success");
              })
              .catch(() => show("Could not add the entry"));
          }}
        />
      ) : null}
    </Card>
  );
}

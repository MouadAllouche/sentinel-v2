"use client";

import { useEffect, useState } from "react";

import { DriftPage, type DriftPath, type DriftSnapshotView } from "@/components/drift/DriftPage";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { client } from "@/lib/api/client";
import { useApiList } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";

export function DriftRoute() {
  const me = useMe();
  const { show } = useToast();
  const paths = useApiList<DriftPath>("/api/drift/paths");
  const status = useApiList<Record<string, unknown>>("/api/drift/status");
  const [selected, setSelected] = useState<DriftPath | null>(null);
  const [snapshots, setSnapshots] = useState<DriftSnapshotView[]>([]);

  useEffect(() => {
    if (!selected) return;
    void client
      .GET("/api/drift/paths/{identifier}/history", {
        params: { path: { identifier: selected.id } },
      })
      .then(({ data }) => setSnapshots((data as unknown as DriftSnapshotView[]) ?? []))
      .catch(() => setSnapshots([]));
  }, [selected]);

  const rows: DriftPath[] = (paths.data?.items ?? []).map((path) => {
    const current = (status.data?.items ?? []).find(
      (item) => Number(item.id) === Number(path.id),
    );
    return { ...path, baseline_status: String(current?.baseline_status ?? "clean") };
  });

  if (paths.isLoading) return <Skeleton rows={5} />;
  if (paths.isError) return <ErrorState message="Could not load monitored paths." />;
  return (
    <DriftPage
      paths={rows}
      snapshots={snapshots}
      onSelect={setSelected}
      onAccept={(identifier, reason) => {
        void client
          .POST("/api/drift/accept", { body: { path: selected?.path ?? "", reason } })
          .then(() => {
            show("Baseline accepted", "success");
            void status.refetch();
            void identifier;
          })
          .catch(() => show("Could not accept the baseline"));
      }}
      onCheck={() => {
        void client
          .POST("/api/drift/check")
          .then(() => {
            show("Drift check complete", "success");
            void status.refetch();
          })
          .catch(() => show("Could not run the drift check"));
      }}
      role={me.role}
    />
  );
}

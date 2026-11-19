"use client";

import { useParams } from "next/navigation";

import { IncidentDetail } from "./IncidentDetail";
import { ErrorState } from "@/components/ui/primitives";

export function IncidentDetailRoute() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  return Number.isFinite(id) && id > 0 ? (
    <IncidentDetail id={id} />
  ) : (
    <ErrorState message="Invalid incident id." />
  );
}

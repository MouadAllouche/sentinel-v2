"use client";

import Link from "next/link";

import { Card, ErrorState, Skeleton } from "@/components/ui/primitives";

export function KpiCard({
  label,
  value,
  delta,
  href,
  loading = false,
  error,
  onRetry,
}: {
  label: string;
  value: string | number;
  delta?: string;
  href: string;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}) {
  return (
    <Card>
      {loading ? (
        <Skeleton rows={2} />
      ) : error ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : (
        <Link href={href} className="block rounded focus-visible:underline">
          <p className="text-sm text-slate-500">{label}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
          {delta ? <p className="mt-1 text-xs text-slate-500">{delta}</p> : null}
        </Link>
      )}
    </Card>
  );
}

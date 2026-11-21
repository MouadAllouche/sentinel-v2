"use client";

import { ErrorState } from "@/components/ui/primitives";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // Log during render (not in an effect): error boundaries may never commit a
  // subtree, and silent errors are impossible to diagnose in production.
  console.error(
    `[sentinel-error] message=${error.message} digest=${error.digest ?? "none"}\n${error.stack ?? ""}`,
  );

  return (
    <div className="p-6">
      <ErrorState message="Something went wrong while rendering this page." onRetry={reset} />
    </div>
  );
}

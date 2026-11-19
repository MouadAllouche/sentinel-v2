"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/ui/primitives";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="p-6">
      <ErrorState message="Something went wrong while rendering this page." onRetry={reset} />
    </div>
  );
}

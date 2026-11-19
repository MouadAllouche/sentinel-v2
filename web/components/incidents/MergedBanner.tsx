import Link from "next/link";

export function MergedBanner({ targetId }: { targetId: number }) {
  return (
    <div role="note" className="rounded border border-blue-300 bg-blue-50 p-3 text-sm dark:border-blue-700 dark:bg-blue-950">
      This incident was merged into{" "}
      <Link className="text-blue-700 underline dark:text-blue-300" href={`/incidents/${targetId}`}>
        Incident #{targetId}
      </Link>
      . Evidence remains available for audit.
    </div>
  );
}

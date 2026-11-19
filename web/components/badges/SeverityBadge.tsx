import { cn } from "@/lib/utils";

const STYLES: Record<string, string> = {
  low: "border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-200",
  medium:
    "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200",
  high:
    "border-orange-400 bg-orange-50 text-orange-900 dark:border-orange-700 dark:bg-orange-950 dark:text-orange-200",
  critical:
    "border-red-400 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-200",
};

/** Severity is always conveyed by text and an icon, never by colour alone. */
export function SeverityBadge({ severity }: { severity: string }) {
  const key = severity.toLowerCase();
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        STYLES[key] ?? STYLES.medium,
      )}
    >
      <span aria-hidden="true" className="text-[10px]">
        ◆
      </span>
      {severity}
    </span>
  );
}

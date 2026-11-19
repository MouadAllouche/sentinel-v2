import { cn } from "@/lib/utils";

export function strengthLabel(strength: string): string {
  return strength.toLowerCase() === "strong" ? "Strong link" : "Weak link";
}

export function StrengthBadge({ strength }: { strength: string }) {
  const strong = strength.toLowerCase() === "strong";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs",
        strong
          ? "border-emerald-600 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100"
          : "border-dashed border-slate-400 text-slate-700 dark:text-slate-300",
      )}
    >
      <span aria-hidden="true">{strong ? "■" : "□"}</span>
      {strengthLabel(strength)}
    </span>
  );
}

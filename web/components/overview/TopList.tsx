import Link from "next/link";

import { Card } from "@/components/ui/primitives";

export function TopList({
  title,
  field,
  items,
  range,
}: {
  title: string;
  field: string;
  items: Array<{ value: string; total: number }>;
  range?: { since: string; until: string };
}) {
  const hrefFor = (value: string) => {
    const params = new URLSearchParams({ [field]: value });
    if (range) {
      params.set("since", range.since);
      params.set("until", range.until);
    }
    return `/events?${params.toString()}`;
  };
  return (
    <Card>
      <h2 className="mb-2 text-sm font-semibold">{title}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">No data yet.</p>
      ) : (
        <ul className="space-y-1 text-sm" aria-label={title}>
          {items.map((item) => (
            <li key={item.value} className="flex justify-between gap-2">
              <Link
                href={hrefFor(item.value)}
                className="truncate text-blue-700 underline dark:text-blue-300"
              >
                {item.value}
              </Link>
              <span className="tabular-nums">{item.total}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
